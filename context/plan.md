# OSCAR Pivot Plan: GitHub-Specialized Coding Assistant

## Overview

Pivot OSCAR from a general OS automation agent to a GitHub-specialized coding assistant with a VS Code extension. Timeline: 2-3 days. Solo developer.

**Target**: A working demo where you open VS Code, interact with OSCAR via a sidebar, compare branches, approve plans, and execute git/shell commands — all powered by Gemini 2.5 Flash.

---

## DAY 1: Backend Foundation

### Step 1.1 — Fix Gemini Client (BLOCKER)

**Why**: The current `planner.py` uses the deprecated `genai.GenerativeModel()` API. The installed `google-genai` v1.67.0 requires `genai.Client().models.generate_content()`. OSCAR will crash on any Gemini call until this is fixed.

**Files to change**:
- `src/oscar/core/planner.py`
  - `_init_client()`: Replace `genai.configure(api_key=api_key); return genai` with `return genai.Client(api_key=api_key)`
  - `_call_llm()`: Replace `self.client.GenerativeModel(model).generate_content(...)` with `self.client.models.generate_content(model=..., contents=..., config={...})`
- `src/oscar/config/llm_config.yaml`
  - Change `active_provider: groq` to `active_provider: gemini`
- `src/oscar/tools/base.py`
  - Update `create_llm_client()` to support Gemini (currently hardcoded to Groq)

**Verify**: Run `oscar --config-check` and `oscar` CLI, type "list files in current directory" — should get a plan from Gemini.

---

### Step 1.2 — Remove Redundant Tools

**Why**: FileOpsTool is 100% redundant with ShellTool. BrowserTool is redundant with WebSearchTool and adds heavy deps (Playwright ~50MB). Neither is registered in the agent anyway.

**Actions**:
- Delete `src/oscar/tools/browser.py`
- Delete `src/oscar/tools/file_ops.py`
- In `pyproject.toml`: remove `playwright`, `beautifulsoup4`, `requests` from dependencies
- In `src/oscar/core/planner.py` line 56: change `available_tools` from `["shell", "web_search", "file_ops"]` to `["shell", "web_search", "git"]`
- In `src/oscar/tools/base.py` `suggest_tool_for_command()`: replace `"browser"` and `"file_ops"` references with `"git"` for git-related keywords
- Run `uv sync` to update lockfile

---

### Step 1.3 — Create GitTool

**Why**: Core feature of the pivot. OSCAR needs native git awareness for branch comparison, PR-style review, and standard git operations.

**New file**: `src/oscar/tools/git_tool.py`

**Design**:
```
class GitTool(BaseTool):
    name = "git"
    description = "Git operations, branch comparison, and code review"

    Commands (routed by first word):
    - status                    → git status
    - diff [args]               → git diff (optional branch/file args)
    - log [args]                → git log --oneline -20
    - commit -m "message"       → git commit -m "message"
    - push [args]               → git push
    - pull [args]               → git pull
    - checkout <branch>         → git checkout <branch>
    - branch [args]             → git branch
    - compare <base> <head>     → git diff base..head → feed to Gemini → return LLM summary
    - review <base> <head>      → git log + diff between branches → feed to Gemini → PR-style commentary
```

**Key details**:
- Extends `BaseTool`, returns `ToolResult` (same pattern as ShellTool)
- Uses `subprocess.run(["git", ...], capture_output=True)`
- `compare` and `review` commands accept an optional `llm_client` (Gemini `genai.Client`) for LLM-powered summaries. If no client, return raw diff.
- `_check_availability()`: verify `shutil.which("git")` is not None
- Safety via `validate_command()`: block `git push --force`, `git reset --hard`, `git clean -f` unless the plan explicitly flags them as high-risk
- For large diffs: truncate to ~50K chars before sending to Gemini (flash has 1M context but no need to waste tokens)

**Register in agent**:
- In `src/oscar/core/agent.py` `_init_tools()`: import and register `GitTool`, pass `self.planner.client` as the LLM client

**Verify**: Run CLI, type "show git status" → should route to GitTool and return output.

---

### Step 1.4 — Rewrite System Prompt for GitHub Focus

**Why**: The LLM needs to know OSCAR is now a GitHub-specialized assistant, not a general OS agent.

**File**: `src/oscar/config/llm_config.yaml`

**Changes to system_prompt**:
- Describe OSCAR as a GitHub-aware coding assistant
- List available tools: `shell` (run commands, tests, builds), `git` (all git ops, branch compare, PR review), `web_search` (docs, Stack Overflow, package info)
- Instruct the LLM to prefer `git` tool for any git/GitHub queries
- Add git-specific plan examples

**Changes to planning_template**:
- Add example plans for git operations
- Add example for branch comparison using the `compare` command

---

### Step 1.5 — Fix Agent Singleton

**Why**: Current `cli/main.py` `process_user_request()` creates a new `OSCARAgent()` on every single request. This wastes time re-initializing planner, tools, and memory. The API server needs a single persistent agent.

**File**: `src/oscar/cli/main.py`

**Change**: Create the agent once at REPL start, reuse it for all requests:
```python
# In main() function, before the while loop:
agent = OSCARAgent()

# In process_user_request(), accept agent as parameter instead of creating new one
def process_user_request(user_input: str, agent: OSCARAgent):
```

---

### Step 1.6 — FastAPI Backend

**Why**: The VS Code extension needs HTTP endpoints to communicate with OSCAR. This wraps the existing pipeline as an API.

**New files**:
- `src/oscar/api/__init__.py` (empty)
- `src/oscar/api/server.py`

**Architecture**: The API splits the current `process_request()` flow into two phases:
1. **Plan phase** (POST /query) — calls `planner.create_plan()` + `SafetyScanner.analyze_plan()`, stores plan, returns it
2. **Execute phase** (POST /run) — takes approval, calls `_execute_plan()`, returns results

This preserves human-in-the-loop: the extension shows the plan and waits for user click before executing.

**Endpoints**:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/query` | Send natural language query, get plan + safety analysis back |
| GET | `/plan/{session_id}` | Get current pending plan |
| POST | `/run/{session_id}` | Approve/reject and execute plan |
| GET | `/history` | Get interaction history |
| GET | `/branches` | List git branches in workspace |
| POST | `/compare` | Compare two branches (LLM-summarized diff) |
| GET | `/memory` | Get current Asterix memory blocks |

**Request/Response models** (Pydantic):
```python
class QueryRequest(BaseModel):
    query: str
    session_id: str = "default"

class QueryResponse(BaseModel):
    session_id: str
    plan: dict          # AgentPlan serialized
    safety: dict        # safety analysis

class RunRequest(BaseModel):
    approved: bool

class CompareRequest(BaseModel):
    base: str           # e.g. "main"
    head: str           # e.g. "feature-branch"
```

**Key implementation detail**: Agent is a singleton initialized on startup. Pending plans stored in a dict keyed by session_id. CORS enabled for VS Code webview origin.

**Dependencies to add** to `pyproject.toml`:
```
"fastapi>=0.100.0",
"uvicorn[standard]>=0.20.0",
```

**Entry point**: Add `oscar-api = "oscar.api.server:run"` to `[project.scripts]` where `run()` calls `uvicorn.run(app, host="127.0.0.1", port=8420)`.

**Verify**: Start server with `oscar-api`, hit `POST /query` with curl:
```bash
curl -X POST http://127.0.0.1:8420/query \
  -H "Content-Type: application/json" \
  -d '{"query": "show git status"}'
```

---

### Step 1.7 — Update Asterix Memory Model

**Why**: Memory adapter hardcodes `model="qwen/qwen3-32b"` (Groq model). Should match the active provider.

**File**: `src/oscar/memory/asterix_adapter.py`

**Change**: Line 53, replace hardcoded model with `settings.get_active_llm_config().model` or just `"gemini-2.5-flash"`.

---

### DAY 1 CHECKPOINT

You should be able to:
1. Run `oscar` CLI → type "compare main and dev" → get LLM-summarized branch diff
2. Run `oscar-api` → POST `/query` with "show me the diff between main and feature" → get structured plan JSON
3. POST `/run/default` with `{"approved": true}` → get execution results
4. POST `/compare` with `{"base": "main", "head": "dev"}` → get LLM summary

---

## DAY 2: VS Code Extension

### Step 2.1 — Extension Scaffold

**New directory**: `vscode-oscar/`

**Structure**:
```
vscode-oscar/
├── .vscode/
│   └── launch.json          # F5 debug config
├── package.json              # Extension manifest
├── tsconfig.json             # TypeScript config
├── src/
│   ├── extension.ts          # Activation, register sidebar provider
│   ├── oscarViewProvider.ts  # WebviewViewProvider (renders sidebar)
│   └── oscarClient.ts       # HTTP client to talk to FastAPI
├── media/
│   ├── main.js               # Webview chat UI logic
│   ├── main.css              # Webview styles
│   └── icon.svg              # OSCAR icon for activity bar
└── README.md
```

**package.json key config**:
- `contributes.viewsContainers.activitybar` — adds OSCAR icon to sidebar
- `contributes.views` — registers webview sidebar panel
- `contributes.configuration` — `oscar.serverUrl` setting (default `http://127.0.0.1:8420`)
- `activationEvents` — activate on view open

**Setup**: `npm init`, install `@types/vscode`, `typescript`, `@vscode/vsce` as dev deps.

---

### Step 2.2 — Sidebar WebviewViewProvider

**File**: `src/oscarViewProvider.ts`

Implements `vscode.WebviewViewProvider`:
- `resolveWebviewView()` sets `webview.html` to the chat UI (inline HTML loading `main.js` + `main.css`)
- `webview.options.enableScripts = true`
- Listens for messages from webview via `webview.onDidReceiveMessage`
- Routes messages to `oscarClient.ts` methods
- Sends responses back via `webview.postMessage()`

**Message protocol** (webview ↔ extension):
```
Webview → Extension:
  { type: "query", text: "compare main and dev" }
  { type: "approve", sessionId: "abc" }
  { type: "reject", sessionId: "abc" }
  { type: "getBranches" }
  { type: "compare", base: "main", head: "dev" }

Extension → Webview:
  { type: "plan", data: { plan, safety, sessionId } }
  { type: "result", data: { execution_result } }
  { type: "branches", data: ["main", "dev", "feature"] }
  { type: "comparison", data: { summary } }
  { type: "error", message: "..." }
```

---

### Step 2.3 — HTTP Client

**File**: `src/oscarClient.ts`

Simple wrapper around `fetch()`:
```typescript
class OscarClient {
    constructor(private baseUrl: string) {}

    async query(text: string, sessionId: string): Promise<QueryResponse>
    async approve(sessionId: string): Promise<RunResponse>
    async reject(sessionId: string): Promise<void>
    async getBranches(): Promise<string[]>
    async compare(base: string, head: string): Promise<CompareResponse>
    async getHistory(): Promise<HistoryEntry[]>
    async getMemory(): Promise<MemoryBlocks>
}
```

Each method is a fetch call to the corresponding FastAPI endpoint. Handle errors gracefully (server not running, timeout, etc.).

---

### Step 2.4 — Webview Chat UI

**File**: `media/main.js` + `media/main.css`

Plain HTML/CSS/JS (no React/Svelte — keep it simple for the timeline).

**Layout**:
```
┌─────────────────────────┐
│  OSCAR Assistant    [⚙] │  ← Header with settings icon
├─────────────────────────┤
│                         │
│  [Chat messages area]   │  ← Scrollable message list
│                         │
│  ┌─ Plan Card ────────┐ │
│  │ Step 1: git diff.. │ │
│  │ Step 2: ...        │ │
│  │ Risk: LOW          │ │
│  │ [Approve] [Reject] │ │  ← Action buttons on plan cards
│  └────────────────────┘ │
│                         │
│  ┌─ Branch Compare ──┐  │
│  │ Base: [dropdown]   │  │
│  │ Head: [dropdown]   │  │
│  │ [Compare]          │  │  ← Branch comparison section
│  └────────────────────┘  │
│                         │
├─────────────────────────┤
│ [Type your query...] [→]│  ← Input area
└─────────────────────────┘
```

**Features**:
- Messages rendered as div cards (user messages right-aligned, OSCAR left-aligned)
- Plan cards show: agent reasoning, step table (tool, command, risk), approve/reject buttons
- Branch comparison: two dropdowns (populated from `/branches`), compare button
- Loading spinners during API calls
- Error messages in red cards
- Auto-scroll to bottom on new messages

**Styling**: Use VS Code's CSS variables (`--vscode-editor-background`, `--vscode-button-background`, etc.) for native look and feel.

---

### Step 2.5 — SSE Streaming for Execution Updates

**Why**: When a multi-step plan is executing, the user should see step-by-step progress in real time, not wait for all steps to finish.

**Backend** (`src/oscar/api/server.py`):
- New endpoint: `POST /run/{session_id}/stream`
- Returns `StreamingResponse` with `text/event-stream` content type
- During `_execute_plan()`, yield SSE events for each step: `data: {"step": 1, "status": "running"}`, `data: {"step": 1, "status": "done", "output": "..."}`

**Frontend** (`media/main.js`):
- Use `EventSource` or `fetch()` with response body stream to consume SSE
- Update plan card steps in real-time (add checkmarks, show output)

**Simplification**: If SSE proves tricky with the webview security model, fall back to polling `/plan/{session_id}` every 500ms during execution.

---

### Step 2.6 — Agent Autonomous Terminal

**Why**: OSCAR should be able to run command sequences (e.g., "run tests") without per-command approval.

**File**: `src/oscar/tools/shell.py`

**Add**:
```python
def execute_sequence(self, commands: List[str], cwd: str = None,
                     stop_on_error: bool = True) -> List[ToolResult]:
    """Run multiple commands in order, capturing all output."""
    results = []
    for cmd in commands:
        result = self.execute(cmd, cwd=cwd)
        results.append(result)
        if not result.success and stop_on_error:
            break
    return results
```

**API**: Add optional `auto_approve` field on `/run` endpoint — only allowed for `low` risk plans. This lets the extension offer a "Run All" button for safe operations.

---

### DAY 2 CHECKPOINT

You should be able to:
1. Open VS Code → see OSCAR icon in activity bar → click → sidebar opens
2. Type "show git status" → see plan card → click Approve → see git status output
3. Use branch comparison dropdowns → click Compare → see LLM diff summary
4. See step-by-step execution progress for multi-step plans

---

## DAY 3: Testing, Polish, Demo

### Step 3.1 — End-to-End Test Scenarios

Test each of these manually:

| # | Scenario | Expected |
|---|----------|----------|
| 1 | "show git status" | Single-step git plan, low risk, shows status |
| 2 | "compare main and dev" | GitTool compare command, LLM summary returned |
| 3 | "create a new branch called demo-feature" | git checkout -b plan, approve, branch created |
| 4 | "run python tests" | Shell plan, executes pytest/test command |
| 5 | "force push to main" | HIGH risk flag, extra confirmation required |
| 6 | "what branches exist?" | GitTool branch -a, parsed list returned |
| 7 | "review changes in feature vs main" | GitTool review command, PR-style commentary |
| 8 | Multiple queries in sequence | Memory persists, session context updates |
| 9 | Server not running | Extension shows "Cannot connect to OSCAR server" error |
| 10 | No git repo in workspace | GitTool returns "Not a git repository" error |

---

### Step 3.2 — Demo Script

Prepare a repo with 2-3 branches that have meaningful diffs. Rehearse this flow:

1. Open VS Code with OSCAR extension visible
2. "What branches exist in this repo?" → shows branch list
3. "Compare main and feature-auth" → shows LLM-summarized diff
4. "Review the changes in feature-auth compared to main" → PR-style commentary
5. "Create a new branch called demo-live" → approve → branch created
6. "Run the test suite" → multi-step plan with autonomous execution
7. Switch to CLI terminal → run `oscar` → same query works there too
8. Show the audit log (`data/logs/audit.jsonl`) to demonstrate logging

---

### Step 3.3 — Error Handling

- **Server not running**: Extension shows connection error with "Start OSCAR server" button/instruction
- **No git repo**: GitTool returns clean error, extension displays it
- **Empty diff**: "These branches are identical" message
- **Huge diff**: Truncate to 50K chars, note "[truncated for analysis]"
- **Gemini rate limit**: Fall back to Groq if available, or show "Rate limited, retry in a moment"
- **Invalid JSON from LLM**: The existing `_clean_json_response()` parser handles this; test with Gemini

---

### Step 3.4 — README + Documentation

Update `README.md`:
- New project description (GitHub-specialized coding assistant)
- Architecture diagram (can reuse/update the mermaid flowchart)
- Installation: `uv sync`, `.env` setup, `playwright install` no longer needed
- Running: `oscar` (CLI) or `oscar-api` (server) + VS Code extension
- Screenshots of the VS Code sidebar in action

---

## DEFERRED (Post-Demo / Future Work)

- [ ] WebSocket bidirectional communication (SSE is sufficient)
- [ ] GitHub API integration via `gh` CLI (PRs, issues, gists)
- [ ] Output chaining between plan steps (step N output → step N+1 context)
- [ ] Extension marketplace packaging (F5 debug launch is fine for demo)
- [ ] Streaming LLM responses (plan returned after full generation)
- [ ] Multi-session / authentication
- [ ] Qdrant vector store for semantic memory retrieval
- [ ] Voice I/O (STT/TTS) — original spec feature, deferred

---

## Dependencies

**Add**:
- `fastapi>=0.100.0`
- `uvicorn[standard]>=0.20.0`

**Remove**:
- `playwright>=1.40.0`
- `beautifulsoup4>=4.12.0`
- `requests>=2.31.0`

**Keep** (even though not primary):
- `groq>=0.4.1` (fallback LLM provider)

**VS Code extension** (npm):
- `@types/vscode`
- `typescript`
- `@vscode/vsce` (for packaging if needed)

---

## File Map (what changes where)

```
MODIFIED:
  src/oscar/core/planner.py        ← Fix Gemini client, update tools list
  src/oscar/core/agent.py          ← Register GitTool, singleton pattern
  src/oscar/cli/main.py            ← Reuse agent singleton
  src/oscar/config/settings.py     ← (minor) no changes needed
  src/oscar/config/llm_config.yaml ← Switch to gemini, rewrite system prompt
  src/oscar/tools/base.py          ← Update suggest_tool, fix create_llm_client
  src/oscar/tools/shell.py         ← Add execute_sequence()
  src/oscar/memory/asterix_adapter.py ← Update model reference
  pyproject.toml                   ← Add fastapi/uvicorn, remove playwright/bs4

DELETED:
  src/oscar/tools/browser.py
  src/oscar/tools/file_ops.py

NEW:
  src/oscar/tools/git_tool.py      ← GitTool with compare/review
  src/oscar/api/__init__.py        ← API package
  src/oscar/api/server.py          ← FastAPI server
  vscode-oscar/                    ← Entire VS Code extension directory
```
