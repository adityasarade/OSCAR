# OSCAR — System Architecture

> Current as of the repo state on the date this document was written. Rendered
> images live alongside this file: `oscar-architecture.png` / `.svg`, and
> `oscar-sequence.png` / `.svg`.

OSCAR is a GitHub-specialized AI coding assistant. It is delivered as a VS Code
extension and CLI, backed by a FastAPI server that wraps an Asterix-based agent
running on Gemini 2.5 Flash (Vertex AI).

---

## 1. System diagram

![OSCAR architecture](oscar-architecture.svg)

```mermaid
flowchart TB
  User([Developer])

  subgraph VSCode["VS Code Extension (TypeScript)"]
    direction TB
    Sidebar["Sidebar WebviewView<br/>(chat UI + branch picker)"]
    Client["OscarClient<br/>(fetch + SSE reader)"]
    Sidebar --> Client
  end

  subgraph FastAPI["FastAPI Server  ·  localhost:8420"]
    direction TB
    Endpoints["Endpoints<br/>/chat  ·  /chat/stream<br/>/chat/confirm  ·  /chat/cancel<br/>/branches  ·  /compare  ·  /review<br/>/history  ·  /memory  ·  /status  ·  /health"]
    Broker["ChatBroker<br/>(asyncio queue · confirm · cancel)"]
    Endpoints --> Broker
  end

  subgraph Agent["OSCAR Agent  (Asterix-powered)"]
    direction TB
    Loop["ReAct loop<br/>reason → tool → observe"]
    Memory["Memory blocks<br/>session_context ·<br/>knowledge_base ·<br/>user_preferences"]
    Patch["asterix_patch<br/>Vertex AI / Gemini bridge"]
    Safety["Safety gate<br/>on_before_tool_call<br/>(low / medium / high / dangerous)"]
    Audit["Audit logger<br/>(JSONL trail)"]
    Loop --> Memory
    Loop --> Safety
    Loop --> Audit
    Loop --> Patch
  end

  subgraph Tools["Tools  (@agent.tool)"]
    direction LR
    Git["git_tool<br/>status · compare · review<br/>log · diff · branches<br/>checkout · commit · push"]
    Shell["shell<br/>(allow-listed subprocess)"]
    Web["web_search<br/>(Tavily, dual-key fallback)"]
    Browser["browser<br/>(Playwright, headless)"]
  end

  subgraph External["External services & storage"]
    direction LR
    Gemini[("Gemini 2.5 Flash<br/>Vertex AI · ADC auth")]
    Tavily[("Tavily API")]
    Chromium[("Chromium<br/>via Playwright")]
    GitRepo[("Local Git<br/>repository")]
    Logs[("data/logs/<br/>audit.jsonl")]
  end

  User -->|prompt · approve · cancel| Sidebar
  Client -->|HTTP + SSE| Endpoints
  Endpoints -->|agent.chat| Loop
  Patch -->|generate_content| Gemini
  Safety -.->|confirm event| Broker
  Broker -.->|step · response · done · error| Client
  Loop --> Git
  Loop --> Shell
  Loop --> Web
  Loop --> Browser
  Git --> GitRepo
  Shell --> GitRepo
  Web --> Tavily
  Browser --> Chromium
  Audit --> Logs

  classDef layer fill:#eef5ff,stroke:#3a6ea5,color:#0b2a4a;
  classDef ext   fill:#fff3cd,stroke:#8a6d3b,color:#3b2e09;
  class VSCode,FastAPI,Agent,Tools layer;
  class External ext;
```

---

## 2. Layered text view (for slides / appendix)

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Developer  ──▶  VS Code Sidebar (WebviewView, TypeScript)                │
│                  • chat UI   • branch picker   • approve / cancel buttons │
│                  └─ OscarClient  (fetch + SSE reader)                     │
└─────────────────────────────────┬─────────────────────────────────────────┘
                                  │  HTTP  +  Server-Sent Events
                                  ▼            (localhost:8420)
┌───────────────────────────────────────────────────────────────────────────┐
│  FastAPI Server  (oscar.api.server)                                       │
│  /chat   /chat/stream   /chat/confirm   /chat/cancel                      │
│  /branches   /compare   /review   /history   /memory   /status   /health  │
│  └─ ChatBroker  (asyncio queue · pending confirms · cancel flag)          │
└─────────────────────────────────┬─────────────────────────────────────────┘
                                  │  agent.chat(message)
                                  ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  OSCAR Agent  (Asterix v0.2.1, patched)                                   │
│  ┌─ ReAct loop ─────────────────────────────────────────────────────────┐ │
│  │   reason → choose tool → execute → observe → repeat                  │ │
│  └──┬──────────────┬─────────────────┬─────────────────┬────────────────┘ │
│     │              │                 │                 │                  │
│  Memory blocks   asterix_patch   Safety gate       Audit logger           │
│  · session_ctx   (Vertex AI /    on_before_        JSONL trail            │
│  · knowledge_b    Gemini bridge)  tool_call        data/logs/audit.jsonl  │
│  · user_prefs                     low / med /                             │
│                                   high / dangerous                        │
└─────────────────────────────────┬─────────────────────────────────────────┘
                                  │  @agent.tool registry
                                  ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  Tools                                                                    │
│  git_tool : status · compare · review · log · diff · branches             │
│             checkout · commit · push                                      │
│  shell    : run_shell_command  (allow-listed subprocess)                  │
│  web      : web_search  (Tavily, dual API-key fallback)                   │
│  browser  : navigate · search · extract · download  (Playwright)          │
└───────┬──────────────┬─────────────────┬────────────────┬─────────────────┘
        │              │                 │                │
        ▼              ▼                 ▼                ▼
  ┌──────────┐  ┌───────────────┐  ┌───────────┐  ┌──────────────┐
  │ Local    │  │ Gemini 2.5    │  │ Tavily    │  │ Chromium     │
  │ Git repo │  │ Flash (Vertex │  │ Search    │  │ (Playwright) │
  │          │  │ AI · ADC)     │  │ API       │  │              │
  └──────────┘  └───────────────┘  └───────────┘  └──────────────┘
```

---

## 3. Sequence — streaming chat with human-in-the-loop confirmation

![OSCAR streaming chat sequence](oscar-sequence.svg)

```mermaid
sequenceDiagram
    autonumber
    actor U as Developer
    participant E as VS Code Sidebar
    participant S as FastAPI /chat/stream
    participant B as ChatBroker
    participant A as OSCAR Agent
    participant G as Gemini (Vertex AI)
    participant T as Tool (e.g. git_push)

    U->>E: type prompt, send
    E->>S: POST /chat/stream { message }
    S->>B: create broker, run agent in worker thread
    A->>G: generate_content(prompt + tools)
    G-->>A: tool_call(git_push, args)
    A->>A: on_before_tool_call → risk=medium
    A->>B: emit { type: confirm, request_id }
    B-->>E: SSE confirm event
    E-->>U: show "Approve / Deny"
    U->>E: click Approve
    E->>S: POST /chat/confirm { id, true }
    S->>B: set_confirm(id, true)
    B-->>A: wait_for_confirm returns true
    A->>T: execute git_push(...)
    T-->>A: result
    A->>B: emit { type: step, "Step 2/8: git_push" }
    A->>G: continue ReAct loop
    G-->>A: final text response
    A->>B: emit { type: response, data }
    B-->>E: SSE response → done
    E-->>U: render final answer
```

---

## 4. Component legend

| Layer    | Component                              | Role                                                                    |
| -------- | -------------------------------------- | ----------------------------------------------------------------------- |
| Client   | VS Code extension (`vscode-oscar/`)    | Sidebar chat UI, branch picker, SSE consumer                            |
| API      | FastAPI server (`oscar.api.server`)    | Stateless HTTP/SSE bridge over the agent singleton                      |
| API      | `ChatBroker` (`oscar.api.runtime`)     | Thread-safe queue connecting agent worker thread to the asyncio loop    |
| Agent    | Asterix `Agent` (`oscar.core.agent`)   | ReAct loop, tool registry, memory blocks                                |
| Agent    | `asterix_patch`                        | Adds Gemini 2.5 Flash / Vertex AI support to Asterix v0.2.1             |
| Agent    | `safety.on_before_tool_call`           | Classifies each call as low / medium / high / dangerous; gates execution|
| Agent    | Audit logger                           | Append-only JSONL log of every tool call                                |
| Tools    | `git_tool`                             | 9 git operations (status, compare, review, log, diff, branches, …)      |
| Tools    | `shell`                                | Cross-platform subprocess runner with safe-command allow-list           |
| Tools    | `web_search`                           | Tavily with dual API-key fallback                                       |
| Tools    | `browser`                              | Playwright/Chromium for navigate, search, extract, download             |
| External | Gemini 2.5 Flash via Vertex AI         | Primary LLM (Application Default Credentials)                           |
| Storage  | `data/logs/audit.jsonl`                | Rotating audit trail of tool calls                                      |

---

## 5. Rebuilding the rendered images

The PNG and SVG images are produced from the `.mmd` sources via the Mermaid CLI:

```bash
npx --yes -p @mermaid-js/mermaid-cli mmdc \
    -i docs/oscar-architecture.mmd \
    -o docs/oscar-architecture.svg \
    -p docs/puppeteer-config.json \
    -b transparent

npx --yes -p @mermaid-js/mermaid-cli mmdc \
    -i docs/oscar-architecture.mmd \
    -o docs/oscar-architecture.png \
    -p docs/puppeteer-config.json \
    -b white -w 2000

# Repeat for oscar-sequence.mmd
```
