# OSCAR — Complete Task List

## Vision

OSCAR is a GitHub-specialized AI coding assistant that lives inside VS Code as a sidebar extension. Users interact with it via natural language to compare branches, review PRs, run commands, and automate git workflows. It uses Asterix (our own agentic framework) as its core orchestrator with Gemini 2.5 Flash via Vertex AI as the LLM. All dangerous operations require human approval before execution.

**Key deliverables:**
- VS Code Marketplace extension with sidebar UI
- GitHub/Git-specialized agent with branch comparison, PR review, diff analysis
- Agent-controlled terminal for running tests, builds, commands
- FastAPI backend bridging the VS Code extension to the Python agent
- Human-in-the-loop safety for all system operations
- Persistent memory across sessions via Asterix

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ VS Code Extension (TypeScript)                       │
│  ├── Sidebar WebviewViewProvider (chat UI)            │
│  ├── Branch comparison widget                        │
│  └── HTTP/SSE client → FastAPI backend               │
├─────────────────────────────────────────────────────┤
│ FastAPI Server (Python)                              │
│  ├── /chat, /branches, /compare, /review, /history   │
│  └── SSE streaming for real-time progress            │
├─────────────────────────────────────────────────────┤
│ OSCAR Agent Layer (Python)                           │
│  ├── Asterix Agent (ReAct loop, memory, state)       │
│  ├── asterix_patch.py (Vertex AI Gemini integration) │
│  ├── Safety callbacks (on_before_tool_call)           │
│  └── Audit logging (on_after_tool_call)              │
├─────────────────────────────────────────────────────┤
│ Tools (registered via @agent.tool())                 │
│  ├── git_* (status, compare, review, log, diff, ...) │
│  ├── shell (subprocess with safety checks)           │
│  ├── web_search (Tavily with dual-key fallback)      │
│  └── browser (Playwright: navigate, extract, click)  │
├─────────────────────────────────────────────────────┤
│ LLM: Gemini 2.5 Flash via Vertex AI (ADC auth)      │
│  Project: oscar-490517 | Region: us-central1         │
└─────────────────────────────────────────────────────┘
```

---

## LLM Configuration

- **Provider:** Vertex AI (NOT Gemini API, NOT Groq)
- **Model:** `gemini-2.5-flash`
- **Auth:** Application Default Credentials (gcloud auth already configured)
- **Project:** `oscar-490517`
- **Location:** `us-central1`
- **Client init:** `Client(vertexai=True, project="oscar-490517", location="us-central1")`
- Asterix v0.2.0 is published with Gemini support. Vertex AI client initialization is being added in a parallel Asterix update. Until then, OSCAR patches Asterix at runtime via `src/oscar/core/asterix_patch.py`.

---

## What's Already Done

- [x] Asterix v0.2.0 published with custom system prompts, execution hooks (on_before/after_tool_call), step callbacks (on_step), history API (get_history)
- [x] Asterix Gemini provider being updated for Vertex AI auth (parallel work in Asterix repo)
- [x] Deleted file_ops.py (redundant with ShellTool)
- [x] Kept browser.py (unique capabilities: navigate, click, extract, download)
- [x] Verified Vertex AI + Gemini 2.5 Flash + Asterix tool calling works end-to-end via OSCAR-side patches
- [x] gcloud ADC auth configured for project oscar-490517

---

## PHASE 1: Core Backend — Rewrite OSCAR on Asterix

### Task 1 — Create `asterix_patch.py` (Vertex AI + Gemini bridge)

**What:** A module that patches Asterix v0.2.0 at runtime to support Gemini via Vertex AI. This module must be imported before creating any Asterix Agent. Once Asterix is updated natively with Vertex AI support, this file can be removed.

**Details:**
- Patch `LLMConfig.__post_init__` to allow `"gemini"` provider
- Add `_call_gemini()` to `LLMProviderManager` with Vertex AI client (`Client(vertexai=True, project="oscar-490517", location="us-central1")`)
- Handle message format translation (OpenAI → Gemini Contents)
- Handle tool schema translation (OpenAI function format → Gemini FunctionDeclaration)
- Handle response translation (Gemini → OpenAI-compatible raw_response for agent.py)
- Add "gemini" to all tracking dicts
- Patch `complete()` to route to `_call_gemini()`
- This code has been tested and verified working

**Files:** `src/oscar/core/asterix_patch.py` (new)

**Depends on:** Nothing — can be done immediately

---

### Task 2 — Rewrite `agent.py` to use Asterix Agent as core orchestrator

**What:** Replace the current custom `OSCARAgent` class with an Asterix `Agent` instance. Import `asterix_patch` first to enable Gemini/Vertex AI.

**Details:**
- Import `asterix_patch` at top of module (enables Gemini before agent creation)
- Create agent with `Agent(agent_id="oscar", model="gemini/gemini-2.5-flash", system_prompt=SYSTEM_PROMPT, blocks={...})`
- Memory blocks: `session_context` (4000, priority 1), `knowledge_base` (3000, priority 2), `user_preferences` (1000, priority 3)
- Wire `on_before_tool_call` → safety callback (auto-approve low risk, prompt for medium+)
- Wire `on_after_tool_call` → audit log (JSONL at `data/logs/audit.jsonl`)
- Wire `on_step` → progress tracking (stored for API streaming)
- Export `get_agent()` singleton
- The main interaction is `agent.chat(user_input)` — Asterix handles the entire ReAct loop

**Files:** `src/oscar/core/agent.py` (rewrite)

**Depends on:** Task 1

---

### Task 3 — Create Git tool functions

**What:** GitHub-specialized git operations as `@agent.tool()` functions. Core differentiator of OSCAR.

**Functions:**
- `git_status()` — repo status, current branch, repo root
- `git_compare(base: str, head: str)` — compare branches: commit count, changed files, diff summary, commit log
- `git_review(branch: str, base: str = "main")` — full diff for code review (truncated at 50K chars), diffstat
- `git_log(branch: str = "HEAD", count: int = 10)` — formatted commit history
- `git_diff(file_path: str, staged: bool = False)` — file-level diff
- `git_branches()` — list local and remote branches
- `git_checkout(branch: str)` — switch branches (medium risk)
- `git_commit(message: str)` — commit staged changes (medium risk)
- `git_push(remote: str = "origin", branch: str = "")` — push to remote (high risk)

All use `subprocess.run(["git", ...], capture_output=True, text=True)`. Each function has clear type hints and docstrings for Asterix schema auto-generation.

**Files:** `src/oscar/tools/git_tool.py` (new)

**Depends on:** Nothing — pure functions, no agent dependency. Tools are registered in Task 2.

---

### Task 4 — Convert shell tool to `@agent.tool()` function

**What:** Convert existing `ShellTool` class into a simple `@agent.tool()` function. Keep the safety validation (safe command allowlist, dangerous pattern regex checks), cross-platform command translation, and timeout handling.

**Function:** `run_shell_command(command: str, cwd: str = "", timeout: int = 30) -> str`

**Files:** `src/oscar/tools/shell.py` (refactor from class to function)

**Depends on:** Nothing — pure function.

---

### Task 5 — Convert web_search tool to `@agent.tool()` function

**What:** Convert existing `WebSearchTool` class into an `@agent.tool()` function. Keep Tavily dual-key fallback.

**Function:** `web_search(query: str) -> str`

**Files:** `src/oscar/tools/web_search.py` (refactor from class to function)

**Depends on:** Nothing — pure function.

---

### Task 6 — Convert browser tool to `@agent.tool()` functions

**What:** Convert existing `BrowserTool` class into `@agent.tool()` functions. Keep Playwright capabilities.

**Functions:**
- `browser_navigate(url: str) -> str`
- `browser_search(query: str) -> str`
- `browser_extract(query: str) -> str`
- `browser_download(url: str) -> str`

**Files:** `src/oscar/tools/browser.py` (refactor from class to functions)

**Depends on:** Nothing — pure functions.

---

### Task 7 — Write GitHub-specialized system prompt

**What:** Create the system prompt that makes OSCAR a GitHub expert.

**Content:**
- Identity: "You are OSCAR, an AI-powered GitHub coding assistant built on the Asterix framework"
- Specialization: branch comparison, PR review, diff analysis, git workflow automation
- Available tools and when to use each
- Git tool usage examples
- Safety: destructive operations (push, reset, delete) will be confirmed by the user via a safety system
- Output: structured, concise, technical, use markdown for diffs/code
- Context: current OS, working directory injected dynamically

**Files:** `src/oscar/config/prompts.py` (new) or inline in `agent.py`

**Depends on:** Nothing — just text.

---

### Task 8 — Adapt safety system for callback pattern

**What:** Refactor `safety.py` into an `on_before_tool_call` callback function.

**Logic:**
1. Check tool name + arguments against `SAFETY_PATTERNS` regex
2. Assess risk: low / medium / high / dangerous
3. Low risk → auto-approve (return True)
4. Medium/high → Rich prompt confirmation (return True/False)
5. Dangerous → require typed "CONFIRM" (return True/False)

Reuse existing `SAFETY_PATTERNS` from `settings.py`.

**Files:** `src/oscar/core/safety.py` (refactor)

**Depends on:** Nothing — pure function.

---

### Task 9 — Update CLI for Asterix-based agent

**What:** Rewrite `main.py` to use the new agent.

**Changes:**
- `get_agent()` returns the Asterix-based singleton from `agent.py`
- `process_user_request()` → just `agent.chat(user_input)` and print the response
- `test_llm_connection()` → `agent.chat("Hello, respond with OK")`
- `display_help()` → GitHub-focused examples
- `display_welcome()` → updated branding
- Add `serve` command to start FastAPI server

**Files:** `src/oscar/cli/main.py` (rewrite)

**Depends on:** Tasks 1, 2 (needs working agent)

---

### Task 10 — Update dependencies and cleanup

**What:** Clean up pyproject.toml, remove obsolete files, update config.

**pyproject.toml:**
- Version → `0.3.0`
- Description → GitHub-focused
- Add: `fastapi>=0.115.0`, `uvicorn[standard]>=0.34.0`
- Ensure: `asterix-agent>=0.2.0`, `google-genai>=1.0.0`
- Add script: `oscar-server = "oscar.api.server:start_server"`

**Remove obsolete files:**
- `src/oscar/core/planner.py` (replaced by Asterix ReAct loop)
- `src/oscar/tools/base.py` (replaced by @agent.tool())
- `src/oscar/memory/asterix_adapter.py` (replaced by direct Asterix Agent)
- `src/oscar/memory/context_manager.py` (empty)
- `src/oscar/memory/persistence.py` (empty)

**Files:** `pyproject.toml`, multiple file deletions

**Depends on:** All other Phase 1 tasks complete

---

## PHASE 2: FastAPI Backend

### Task 11 — Create FastAPI server

**What:** HTTP API wrapping the Asterix-based agent.

**Endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| POST | `/chat` | Natural language query → agent.chat() |
| POST | `/chat/stream` | SSE streaming with step-by-step progress |
| GET | `/history` | Conversation history via agent.get_history() |
| GET | `/branches` | List git branches |
| POST | `/compare` | Compare two branches |
| POST | `/review` | Review branch changes |
| GET | `/memory` | Current Asterix memory blocks |
| GET | `/status` | Agent status |

Agent singleton via `lifespan` context manager. CORS enabled. Pydantic models for all request/response.

**Files:** `src/oscar/api/__init__.py`, `src/oscar/api/server.py` (new)

**Depends on:** Phase 1 complete (working agent with tools)

---

## PHASE 3: VS Code Extension

### Task 12 — Extension scaffold + manifest

**What:** Create `vscode-oscar/` with package.json, tsconfig, launch.json. Register sidebar view container with OSCAR icon in activity bar.

**Files:** `vscode-oscar/package.json`, `vscode-oscar/tsconfig.json`, etc.

**Depends on:** Nothing — can start immediately.

---

### Task 13 — HTTP/SSE client (TypeScript)

**What:** `oscarClient.ts` wrapping fetch() calls to FastAPI endpoints. Includes SSE consumer for `/chat/stream`.

**Files:** `vscode-oscar/src/oscarClient.ts`

**Depends on:** Task 12 (scaffold exists)

---

### Task 14 — WebviewViewProvider (sidebar)

**What:** `oscarViewProvider.ts` implementing `vscode.WebviewViewProvider`. Loads webview HTML, handles message passing between webview and extension.

**Files:** `vscode-oscar/src/oscarViewProvider.ts`

**Depends on:** Task 12

---

### Task 15 — Chat UI (webview frontend)

**What:** Plain HTML/CSS/JS chat interface. Messages area, input box, branch comparison widget, progress indicator. Uses VS Code CSS variables for native theming.

**Files:** `vscode-oscar/media/main.js`, `vscode-oscar/media/main.css`

**Depends on:** Task 12

---

### Task 16 — Extension activation

**What:** `extension.ts` that registers the sidebar provider, reads settings, checks server health on activation.

**Files:** `vscode-oscar/src/extension.ts`

**Depends on:** Tasks 14, 15

---

### Task 17 — Package and publish to VS Code Marketplace

**What:** `vsce package` to create .vsix, publish or side-load for demo.

**Depends on:** All Phase 3 tasks complete + Phase 2 server working

---

## PHASE 4: Testing and Demo

### Task 18 — End-to-end testing

Test scenarios covering CLI, API, VS Code extension, memory persistence, error handling, safety confirmations.

### Task 19 — Demo preparation

Script a demo flow with a prepared repository that has meaningful branches and diffs.

### Task 20 — README and documentation

Updated README with architecture, installation, usage, screenshots.

---

## Dependency Graph

```
PARALLEL GROUP A (no dependencies — start immediately):
  Task 1:  asterix_patch.py (Vertex AI bridge)
  Task 3:  Git tool functions
  Task 4:  Shell tool function
  Task 5:  Web search tool function
  Task 6:  Browser tool functions
  Task 7:  System prompt
  Task 8:  Safety callback
  Task 12: VS Code extension scaffold

SEQUENTIAL GROUP B (depends on Group A):
  Task 2:  agent.py rewrite (needs Tasks 1, 3-8)
  Task 13: HTTP client (needs Task 12)
  Task 14: WebviewViewProvider (needs Task 12)
  Task 15: Chat UI (needs Task 12)

SEQUENTIAL GROUP C (depends on Group B):
  Task 9:  CLI rewrite (needs Task 2)
  Task 10: Cleanup + deps (needs Task 2)
  Task 16: Extension activation (needs Tasks 14, 15)

SEQUENTIAL GROUP D (depends on Group C):
  Task 11: FastAPI server (needs Tasks 2, 9)

SEQUENTIAL GROUP E (depends on Group D):
  Task 17: VS Code publish (needs Tasks 11, 16)
  Task 18: E2E testing (needs everything)
  Task 19: Demo prep
  Task 20: README

```

---

## Deferred / Future Work

- [ ] GitHub API integration via `gh` CLI (PRs, issues, gists, actions)
- [ ] Code generation and file editing capabilities
- [ ] Multi-repo support
- [ ] Voice I/O (STT/TTS)
- [ ] Qdrant vector store for semantic memory retrieval
- [ ] Plugin system for third-party tool extensions
- [ ] Multi-user / authentication
- [ ] WebSocket bidirectional communication
- [ ] Streaming LLM responses (token-by-token)
