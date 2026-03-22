# OSCAR — Complete Task List

## Vision

OSCAR is a GitHub-specialized AI coding assistant that lives inside VS Code as a sidebar extension. Users interact with it via natural language to compare branches, review PRs, run commands, and automate git workflows. It uses Asterix (our own agentic framework) as its core orchestrator with Gemini 2.5 Flash as the primary LLM. All dangerous operations require human approval before execution.

**Key deliverables:**
- VS Code Marketplace extension with sidebar UI
- GitHub/Git-specialized agent with branch comparison, PR review, diff analysis
- Agent-controlled terminal for running tests, builds, commands
- FastAPI backend bridging the VS Code extension to the Python agent
- Human-in-the-loop safety for all system operations
- Persistent memory across sessions via Asterix

---

## What's Already Done

- [x] Asterix v0.2.0 published with Gemini support, custom system prompts, execution hooks, step callbacks, history API
- [x] Fixed Gemini client in planner.py (Task 1 from old plan — will be replaced by Asterix integration)
- [x] Deleted file_ops.py (redundant with ShellTool)
- [x] Kept browser.py (unique capabilities: navigate, click, extract, download — Tavily alternative)
- [x] Updated planner.py available_tools and prompt tool options

---

## PHASE 1: Core Backend — Rewrite OSCAR on Asterix

### Task 1 — Rewrite `agent.py` to use Asterix `Agent` as core orchestrator

**What:** Replace the current custom `OSCARAgent` class (which manually calls planner → safety → confirm → execute) with an Asterix `Agent` instance. The Asterix agent handles the ReAct loop, tool routing via LLM function calling, memory management, and state persistence automatically.

**Details:**
- Create the Asterix agent with `model="gemini/gemini-2.5-flash"` and a GitHub-specialized `system_prompt`
- Define memory blocks: `session_context`, `knowledge_base`, `user_preferences` (matching current adapter)
- Wire `on_before_tool_call` to OSCAR's safety scanner for human-in-the-loop confirmation
- Wire `on_after_tool_call` to audit logging (JSONL)
- Wire `on_step` for progress tracking (used later by the API for streaming)
- Export a `get_agent()` singleton for CLI and API to share
- Keep the existing audit log path (`data/logs/audit.jsonl`)

**Files:** `src/oscar/core/agent.py` (rewrite), `src/oscar/core/safety.py` (adapt for callback pattern)

---

### Task 2 — Register tools via `@agent.tool()`

**What:** Convert existing OSCAR tools (shell, web_search, browser) and create new ones (git) as Asterix `@agent.tool()` decorated functions. This replaces the custom `BaseTool`/`ToolRegistry` system with Asterix's native tool routing via LLM function calling — no more hardcoded keyword matching.

**Details:**
- **Shell tool**: Register function wrapping `subprocess.run()` with safety validation. Parameters: `command: str`, optional `cwd: str`, optional `timeout: int`. Include the safe command allowlist and dangerous pattern checks from current `ShellTool`.
- **Git tool**: New. Register functions for each git operation (see Task 3).
- **Web search tool**: Register function wrapping existing Tavily search with dual-key fallback.
- **Browser tool**: Register function wrapping existing Playwright capabilities (navigate, search, extract, download).
- Each tool function should have clear type hints and docstrings — Asterix auto-generates LLM function calling schemas from these.

**Files:** `src/oscar/tools/` (refactor all tools as `@agent.tool()` functions)

---

### Task 3 — Create Git tool functions

**What:** GitHub-specialized git operations registered as `@agent.tool()` functions. This is the core differentiator of OSCAR.

**Functions to register:**
- `git_status()` — returns repo status, current branch, repo root
- `git_compare(base: str, head: str)` — compare two branches: commit count, changed files, diff summary, commit log between them
- `git_review(branch: str, base: str = "main")` — full diff for code review (truncated at 50K chars for LLM context), diffstat summary
- `git_log(branch: str = "HEAD", count: int = 10)` — formatted commit history with hash, author, date, message
- `git_diff(file_path: str, staged: bool = False)` — file-level diff
- `git_branches()` — list all local and remote branches
- `git_checkout(branch: str)` — switch branches (medium risk — needs confirmation)
- `git_commit(message: str)` — commit staged changes (medium risk)
- `git_push(remote: str = "origin", branch: str = "")` — push to remote (high risk — needs confirmation)

All functions use `subprocess.run(["git", ...], capture_output=True, text=True)`. The compare and review functions are the most valuable for the demo — they produce structured output that the LLM can summarize intelligently.

**Files:** `src/oscar/tools/git_tool.py` (new)

---

### Task 4 — Write GitHub-specialized system prompt

**What:** Create the system prompt that makes OSCAR a GitHub expert. This is passed as `system_prompt=` to the Asterix Agent constructor.

**Content should include:**
- Identity: "You are OSCAR, an AI-powered GitHub coding assistant"
- Specialization: branch comparison, PR review, diff analysis, git workflow automation
- Available tools and when to use each (shell for commands, git for repo operations, web_search for docs/Stack Overflow, browser for web pages)
- Git tool usage examples (compare, review, log, diff, branches)
- Safety rules: always use `request_confirmation` or rely on the on_before_tool_call hook for destructive operations
- Output format preferences: structured, concise, technical
- Context: current OS, working directory

**Files:** `src/oscar/config/llm_config.yaml` (rewrite) or inline in agent.py

---

### Task 5 — Adapt safety system for callback pattern

**What:** The current `safety.py` has a `SafetyScanner` that displays Rich tables and prompts for confirmation. This needs to be adapted into an `on_before_tool_call` callback function that:
1. Checks the tool name and arguments against safety patterns
2. Assesses risk level (low/medium/high/dangerous)
3. For low risk: auto-approve (return True)
4. For medium/high: prompt user with Rich confirmation (return True/False)
5. For dangerous: require typed "CONFIRM" (return True/False)

The existing regex patterns in `SAFETY_PATTERNS` and the risk assessment logic can be reused. The Rich display needs to be simpler since it's now per-tool-call, not per-plan.

**Files:** `src/oscar/core/safety.py` (refactor)

---

### Task 6 — Update CLI for Asterix-based agent

**What:** Rewrite `main.py` to use the Asterix-based agent. The main change: instead of calling `agent.process_request()` (which internally did plan → confirm → execute), now just call `agent.chat(user_input)`. Asterix handles the entire ReAct loop, tool calling, and confirmation via callbacks.

**Details:**
- `get_agent()` singleton returns the Asterix-based agent
- `process_user_request(input)` becomes `agent.chat(input)` — much simpler
- `test_llm_connection()` uses `agent.chat("Hello, respond with OK")`
- `test_agent_components()` checks agent status, tool count, memory blocks
- `display_help()` updated for GitHub-focused usage examples
- `display_welcome()` updated branding

**Files:** `src/oscar/cli/main.py` (rewrite)

---

### Task 7 — Update dependencies and config

**What:** Clean up pyproject.toml and config files for the new architecture.

**pyproject.toml changes:**
- Version: `0.3.0`
- Description: `"OSCAR - GitHub-Specialized AI Coding Assistant"`
- Remove: `playwright>=1.40.0` (if browser tool is also converted, otherwise keep)
- Add: `fastapi>=0.115.0`, `uvicorn[standard]>=0.34.0`
- Ensure: `asterix-agent>=0.2.0`, `google-genai>=1.0.0`
- Update keywords: add `github`, `code-review`, `git`, `vscode`
- Add script: `oscar-server = "oscar.api.server:start_server"`

**llm_config.yaml changes:**
- `active_provider: gemini`
- Keep groq as fallback config
- System prompt can be moved here or kept in agent.py

**Files:** `pyproject.toml`, `src/oscar/config/llm_config.yaml`

---

### Task 8 — Remove/refactor obsolete modules

**What:** With Asterix as the orchestrator, several OSCAR modules become obsolete or need significant simplification.

- `src/oscar/core/planner.py` — **Remove or simplify.** Asterix's agent handles LLM calls and plan generation internally via its ReAct loop. The `LLMPlanner` class, `AgentPlan`/`ActionStep` models, and all the JSON parsing logic are no longer needed. If we still want a "plan mode" (show plan before executing), this could become a lightweight wrapper.
- `src/oscar/tools/base.py` — **Simplify.** `BaseTool`, `ToolRegistry`, `suggest_tool_for_command()` are all replaced by Asterix's `@agent.tool()` system. Keep only `ToolResult` if any tool functions still use it, or remove entirely.
- `src/oscar/memory/asterix_adapter.py` — **Remove.** The Asterix `Agent` now handles memory blocks directly. The adapter was a bridge that's no longer needed.
- `src/oscar/memory/context_manager.py`, `persistence.py` — **Remove.** Already empty files.

**Files:** Multiple files to remove or simplify

---

## PHASE 2: FastAPI Backend

### Task 9 — Create FastAPI server

**What:** HTTP API wrapping the Asterix-based agent for the VS Code extension to consume.

**Endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check — git available, agent ready, repo root |
| POST | `/chat` | Send natural language query, get response (agent.chat()) |
| GET | `/history` | Get conversation history (agent.get_history()) |
| GET | `/branches` | List git branches in workspace |
| POST | `/compare` | Compare two branches — returns structured diff + LLM summary |
| POST | `/review` | Review branch changes — returns PR-style commentary |
| GET | `/memory` | Get current Asterix memory blocks |
| GET | `/status` | Agent status — tools, memory, conversation stats |

**Design notes:**
- Agent is a singleton initialized on startup via `lifespan` context manager
- CORS enabled for VS Code webview origin
- Pydantic request/response models for all endpoints
- The `/chat` endpoint is the primary interface — it passes the query to `agent.chat()` and returns the response
- For the `/chat` endpoint, the `on_before_tool_call` callback should auto-approve low-risk operations (since the extension has its own approval UI — see Phase 3)
- SSE streaming endpoint (`/chat/stream`) for real-time step updates using the `on_step` callback — returns `text/event-stream` with step-by-step progress

**Files:** `src/oscar/api/__init__.py` (new), `src/oscar/api/server.py` (new)

---

### Task 10 — Add `serve` command to CLI

**What:** Users should be able to start the API server from the OSCAR CLI.

- Add `oscar-server` script entry point in pyproject.toml
- Add `serve` command in CLI's main REPL loop
- Server starts on `127.0.0.1:8420` by default

**Files:** `src/oscar/cli/main.py`, `pyproject.toml`

---

## PHASE 3: VS Code Extension

### Task 11 — Extension scaffold and manifest

**What:** Create the VS Code extension project with proper structure.

**Directory:** `vscode-oscar/`

**Structure:**
```
vscode-oscar/
├── .vscode/
│   └── launch.json              # F5 debug launch config
├── .vscodeignore                # Files to exclude from package
├── package.json                 # Extension manifest
├── tsconfig.json                # TypeScript config
├── src/
│   ├── extension.ts             # Activation, register sidebar provider
│   ├── oscarViewProvider.ts     # WebviewViewProvider implementation
│   └── oscarClient.ts          # HTTP/SSE client to talk to FastAPI
├── media/
│   ├── main.js                  # Webview chat UI logic
│   ├── main.css                 # Webview styles (VS Code theme vars)
│   └── icon.svg                 # OSCAR icon for activity bar
└── README.md
```

**package.json key config:**
- `contributes.viewsContainers.activitybar` — OSCAR icon in sidebar
- `contributes.views` — webview sidebar panel
- `contributes.configuration` — `oscar.serverUrl` setting (default `http://127.0.0.1:8420`)
- `activationEvents` — activate on view open

**Files:** Entire `vscode-oscar/` directory (new)

---

### Task 12 — WebviewViewProvider (sidebar panel)

**What:** TypeScript class implementing `vscode.WebviewViewProvider` that renders the OSCAR sidebar.

**Details:**
- `resolveWebviewView()` sets HTML with embedded JS/CSS
- Listens for messages from webview via `webview.onDidReceiveMessage`
- Routes messages to `oscarClient.ts`
- Sends responses back via `webview.postMessage()`

**Message protocol (webview <-> extension):**
```
Webview → Extension:
  { type: "chat", text: "compare main and dev" }
  { type: "getBranches" }
  { type: "compare", base: "main", head: "dev" }
  { type: "getHistory" }

Extension → Webview:
  { type: "response", data: { message: "..." } }
  { type: "branches", data: ["main", "dev", "feature"] }
  { type: "comparison", data: { summary: "..." } }
  { type: "history", data: [...] }
  { type: "step", data: { step: 1, max: 5, tools: ["git_compare"] } }
  { type: "error", message: "..." }
```

**Files:** `vscode-oscar/src/oscarViewProvider.ts`

---

### Task 13 — HTTP/SSE client

**What:** TypeScript wrapper around `fetch()` for all FastAPI endpoints.

**Methods:**
- `chat(text: string): Promise<ChatResponse>`
- `getBranches(): Promise<string[]>`
- `compare(base: string, head: string): Promise<CompareResponse>`
- `review(branch: string, base?: string): Promise<ReviewResponse>`
- `getHistory(limit?: number): Promise<HistoryEntry[]>`
- `getMemory(): Promise<MemoryBlocks>`
- `chatStream(text: string, onStep: callback): Promise<void>` — SSE consumer for real-time updates

**Files:** `vscode-oscar/src/oscarClient.ts`

---

### Task 14 — Chat UI (webview frontend)

**What:** Plain HTML/CSS/JS chat interface rendered inside the VS Code sidebar webview.

**Layout:**
```
┌─────────────────────────┐
│  OSCAR Assistant        │  Header
├─────────────────────────┤
│                         │
│  [Chat messages area]   │  Scrollable messages
│                         │
│  ┌─ Agent Response ───┐ │
│  │ Here's the diff... │ │
│  │ (with formatting)  │ │
│  └────────────────────┘ │
│                         │
│  ┌─ Branch Compare ──┐  │
│  │ Base: [dropdown]   │  │
│  │ Head: [dropdown]   │  │
│  │ [Compare]          │  │  Branch comparison widget
│  └────────────────────┘  │
│                         │
│  ┌─ Progress ─────────┐ │
│  │ Step 2/4: git_log  │ │  Real-time step progress
│  │ ████████░░ 50%     │ │
│  └────────────────────┘ │
│                         │
├─────────────────────────┤
│ [Type your query...] [→]│  Input area
└─────────────────────────┘
```

**Features:**
- Messages as div cards (user right-aligned, OSCAR left-aligned)
- Markdown rendering for agent responses (code blocks, diffs)
- Branch comparison section with dropdowns populated from `/branches`
- Real-time step progress during multi-tool operations
- Loading spinners during API calls
- Error messages in red
- Uses VS Code CSS variables (`--vscode-editor-background`, etc.) for native look

**Files:** `vscode-oscar/media/main.js`, `vscode-oscar/media/main.css`

---

### Task 15 — Extension activation and registration

**What:** Main `extension.ts` that registers the sidebar provider and handles activation.

**Details:**
- Register `OscarViewProvider` as a `WebviewViewProvider`
- Read `oscar.serverUrl` from VS Code settings
- On activation, check if OSCAR server is reachable (GET /health)
- Show notification if server is not running

**Files:** `vscode-oscar/src/extension.ts`

---

### Task 16 — Package and publish to VS Code Marketplace

**What:** Package the extension and publish it.

**Steps:**
- Install `@vscode/vsce` for packaging
- Create a publisher account on VS Code Marketplace (if not already)
- Add `publisher` field to package.json
- Add icon, description, categories, tags
- `vsce package` to create `.vsix` file
- `vsce publish` to publish (or side-load for demo with `code --install-extension oscar-0.1.0.vsix`)

**Files:** `vscode-oscar/package.json` (metadata), `vscode-oscar/.vscodeignore`

---

## PHASE 4: Testing and Demo

### Task 17 — End-to-end testing

**Test scenarios:**
1. CLI: `oscar` → type "show git status" → agent calls git_status tool → shows result
2. CLI: "compare main and dev" → agent calls git_compare → LLM summarizes diff
3. CLI: "review the changes on feature branch" → agent calls git_review → PR-style commentary
4. CLI: "run python tests" → agent calls shell tool → on_before_tool_call asks for confirmation → executes
5. CLI: "force push to main" → high risk → strong confirmation required
6. API: `curl POST /chat` → returns agent response
7. API: `curl GET /branches` → returns branch list
8. API: `curl POST /compare` → returns structured comparison
9. VS Code: Open sidebar → type query → see response with formatting
10. VS Code: Use branch comparison widget → see LLM-summarized diff
11. VS Code: Multi-step operation → see real-time progress updates
12. Memory: Multiple queries in sequence → session context persists
13. Error: No git repo → clean error message
14. Error: Server not running → extension shows connection error

---

### Task 18 — Demo preparation

**Script a demo flow:**
1. Open VS Code with OSCAR extension visible in sidebar
2. "What branches exist in this repo?" → shows branch list
3. "Compare main and feature-auth" → LLM-summarized diff
4. "Review the changes in feature-auth vs main" → PR-style code review
5. "Create a new branch called demo-live" → confirmation → branch created
6. "Run the test suite" → multi-step execution with progress
7. Show audit log (`data/logs/audit.jsonl`)
8. Switch to CLI → same queries work there too

**Prepare:** A demo repository with 2-3 branches that have meaningful, reviewable diffs.

---

### Task 19 — README and documentation

**Update README.md with:**
- New project description (GitHub-specialized AI coding assistant)
- Architecture overview (Asterix agent + FastAPI + VS Code extension)
- Installation instructions (Python backend + VS Code extension)
- Usage examples with screenshots
- How to run: `oscar` (CLI), `oscar-server` (API), VS Code extension

---

## Deferred / Future Work

- [ ] GitHub API integration via `gh` CLI (PRs, issues, gists, actions)
- [ ] Code generation and file editing capabilities
- [ ] Multi-repo support
- [ ] Voice I/O (STT/TTS) — original spec feature
- [ ] Qdrant vector store for semantic memory retrieval
- [ ] Plugin system for third-party tool extensions
- [ ] Multi-user / authentication for shared servers
- [ ] WebSocket bidirectional communication (SSE is sufficient for now)
- [ ] Streaming LLM responses (token-by-token)
