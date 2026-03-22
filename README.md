# OSCAR — GitHub-Specialized AI Coding Assistant

A VS Code extension and CLI powered by the [Asterix](https://github.com/adityasarade/asterix) agentic framework and **Gemini 2.5 Flash** via Vertex AI. Specialized for GitHub workflows: branch comparison, PR review, diff analysis, and git automation.

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
│  └── browser (Playwright: navigate, extract, search) │
├─────────────────────────────────────────────────────┤
│ LLM: Gemini 2.5 Flash via Vertex AI (ADC auth)      │
│  Project: oscar-490517 | Region: us-central1         │
└─────────────────────────────────────────────────────┘
```

## Features

- **Git-specialized tools** — status, branch compare, PR review, log, diff, checkout, commit, push
- **Browser automation** — navigate, search, extract content, download files (Playwright)
- **Web search** — Tavily-based with dual API key fallback
- **Shell execution** — cross-platform command runner with safe-command allowlist
- **Human-in-the-loop safety** — auto-approve low risk, confirm medium/high, typed `CONFIRM` for dangerous ops
- **Persistent memory** — session context, knowledge base, user preferences via Asterix memory blocks
- **Streaming progress** — Server-Sent Events through FastAPI for real-time updates
- **VS Code sidebar** — chat UI with branch comparison widget (in development)

## Installation

### Prerequisites

- Python >= 3.10
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (for Vertex AI auth)

### Python Backend

```bash
git clone https://github.com/adityasarade/OSCAR.git
cd OSCAR
pip install -e .
playwright install chromium
```

#### Vertex AI Authentication

```bash
gcloud auth application-default login
```

#### Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Required | Description |
|---|---|---|
| `TAVILY_API_KEY1` | Optional | Tavily web search API key |
| `TAVILY_API_KEY2` | Optional | Fallback Tavily key for rate-limit rotation |

Vertex AI auth uses Application Default Credentials — no API key needed if `gcloud auth` is configured.

### VS Code Extension (in development)

```bash
cd vscode-oscar
npm install
npm run compile
# Press F5 in VS Code to launch Extension Development Host
```

## Usage

### CLI

```bash
oscar                  # Start interactive session
oscar --debug          # Debug mode
oscar --dry-run        # Dry run (no destructive ops)
oscar --config-check   # Verify configuration
```

Example session:

```
OSCAR> git status
OSCAR> compare main and feature-branch
OSCAR> review feature-branch against main
OSCAR> search for Python async best practices
OSCAR> navigate to https://docs.python.org
```

### VS Code (in development)

Open the OSCAR sidebar from the activity bar to chat with the agent. The extension communicates with the FastAPI backend over HTTP/SSE.

## Project Structure

```
src/oscar/
├── cli/main.py              # CLI entry point
├── config/settings.py       # Configuration and safety patterns
├── core/
│   ├── agent.py             # Asterix agent orchestrator
│   ├── asterix_patch.py     # Vertex AI + Gemini runtime bridge
│   └── safety.py            # Human-in-the-loop safety callbacks
└── tools/
    ├── git_tool.py          # Git operations (9 functions)
    ├── shell.py             # Shell command execution
    ├── web_search.py        # Tavily web search
    └── browser.py           # Playwright browser automation
```

## Built With

- **[Asterix](https://github.com/adityasarade/asterix)** — Agentic framework (ReAct loop, memory, tool management)
- **Gemini 2.5 Flash** — LLM via Google Vertex AI
- **FastAPI** — HTTP backend with SSE streaming
- **Playwright** — Headless browser automation
- **Tavily** — Web search API
- **Rich** — Terminal UI and formatting
- **Click** — CLI framework
- **TypeScript** — VS Code extension

## License

MIT

## Author

Built by **Aditya Sarade** — Final year AI & Data Science, AISSMS IOIT, Pune.
