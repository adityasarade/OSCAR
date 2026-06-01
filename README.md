# OSCAR — GitHub-Specialized AI Coding Assistant

A VS Code extension and CLI powered by the [Asterix](https://github.com/adityasarade/asterix) agentic framework. Specialized for GitHub workflows: branch comparison, PR review, diff analysis, and git automation. **Bring your own LLM** — Gemini, OpenAI GPT-5, Anthropic Claude 4, Groq, or local Ollama models, switchable with a single environment variable.

## What's new in v0.6.2

- **Catalog refresh after full online syntax fact-check** against platform.claude.com, ai.google.dev, developers.openai.com, and docs.ollama.com.
- **Claude Opus 4.8** added (released 2026-05-28); Opus 4.7 retained as legacy.
- **Anthropic tool_choice** translation now accepts both `{"type":"function","function":{"name":"x"}}` (legacy) and `{"type":"function","name":"x"}` (current) OpenAI shapes.

## What's new in v0.6.1

- **Multi-provider LLM support.** Switch between Gemini, OpenAI, Anthropic, Groq, and Ollama via `OSCAR_LLM_PROVIDER` / `OSCAR_LLM_MODEL`.
- **26-model catalog** including GPT-5.5 / 5.4 family, Claude 4 family (opus/sonnet/haiku), Gemini 3.5/3.1/2.5, and popular open-source models on Ollama.
- New `/providers` API endpoint and `oscar providers` CLI command for discovering supported models.
- VS Code status-bar item showing the active provider/model, with a quick-pick command (`OSCAR: Select LLM provider and model`) to switch.
- **Fixed in 0.6.1:** OpenAI reasoning models (`gpt-5.5`, `gpt-5.4`, `o3`, `o4-mini`) now correctly send `max_completion_tokens` and skip `temperature` (Asterix's native handler only knew about a few of these — picking `o3` previously would crash). Ollama calls no longer send `tool_choice` (which the OpenAI-compat layer rejects). Gemini default stays on `gemini-2.5-flash` because the 3.5-flash Vertex AI rollout is still region-gated.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ VS Code Extension (TypeScript)                       │
│  ├── Sidebar WebviewViewProvider (chat UI)            │
│  ├── Status-bar provider/model indicator              │
│  ├── Quick-pick model switcher                        │
│  └── HTTP/SSE client → FastAPI backend                │
├─────────────────────────────────────────────────────┤
│ FastAPI Server (Python)                              │
│  ├── /chat, /branches, /compare, /review, /history    │
│  ├── /providers (multi-provider model catalog)        │
│  └── SSE streaming for real-time progress             │
├─────────────────────────────────────────────────────┤
│ OSCAR Agent Layer (Python)                           │
│  ├── Asterix Agent (ReAct loop, memory, state)        │
│  ├── asterix_patch.py — multi-provider LLM bridge     │
│  ├── Safety callbacks (on_before_tool_call)           │
│  └── Audit logging (on_after_tool_call)               │
├─────────────────────────────────────────────────────┤
│ Tools (registered via @agent.tool())                 │
│  ├── git_* (status, compare, review, log, diff, ...)  │
│  ├── shell (subprocess with safety checks)            │
│  ├── web_search (Tavily with dual-key fallback)       │
│  └── browser (Playwright: navigate, extract, search)  │
├─────────────────────────────────────────────────────┤
│ LLM providers (pick one)                             │
│  ├── Gemini · 2.5 Pro / Flash / Flash-Lite / 2.0 Flash │
│  ├── OpenAI · GPT-5 · GPT-5 mini · GPT-5 nano · o3 ··· │
│  ├── Anthropic · Claude Opus/Sonnet/Haiku 4.x          │
│  ├── Groq    · Llama 3.3 70B Versatile · 3.1 8B Instant│
│  └── Ollama  · Llama 3.3 / Qwen 2.5 Coder / DeepSeek …  │
└─────────────────────────────────────────────────────┘
```

## Features

- **Git-specialized tools** — status, branch compare, PR review, log, diff, checkout, commit, push
- **Multi-provider LLM** — five providers, 21 catalogued models, configurable primary + fallback
- **Browser automation** — navigate, search, extract content, download files (Playwright)
- **Web search** — Tavily-based with dual API key fallback
- **Shell execution** — cross-platform command runner with safe-command allowlist
- **Human-in-the-loop safety** — auto-approve low risk, confirm medium/high, typed `CONFIRM` for dangerous ops
- **Persistent memory** — session context, knowledge base, user preferences via Asterix memory blocks
- **Streaming progress** — Server-Sent Events through FastAPI for real-time updates
- **VS Code sidebar** — chat UI with branch comparison widget and status-bar model picker

## Installation

### Prerequisites

- Python >= 3.10
- (Optional) [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) — only needed for the Gemini/Vertex AI default
- (Optional) [Ollama](https://ollama.ai/) — only needed if you want local models

### Python Backend

```bash
git clone https://github.com/adityasarade/OSCAR.git
cd OSCAR
pip install -e .
playwright install chromium
```

### Choose your LLM provider

OSCAR ships with five providers ready to use. Copy `.env.example` to `.env` and set the provider you want:

```bash
cp .env.example .env
```

| Provider | Set in `.env` | Credentials |
|---|---|---|
| **Gemini** (default) | `OSCAR_LLM_PROVIDER=gemini` | `gcloud auth application-default login` (or `GEMINI_API_KEY`) |
| **OpenAI** | `OSCAR_LLM_PROVIDER=openai` | `OPENAI_API_KEY` |
| **Anthropic Claude** | `OSCAR_LLM_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |
| **Groq** | `OSCAR_LLM_PROVIDER=groq` | `GROQ_API_KEY` |
| **Ollama** (local) | `OSCAR_LLM_PROVIDER=ollama` | none — just have Ollama running locally |

The full model catalog, with recommendations:

| Provider | Models |
|---|---|
| **Gemini** | `gemini-2.5-flash` ★ · `gemini-3.5-flash`† · `gemini-3.1-pro-preview`† · `gemini-3.1-flash-lite`† · `gemini-2.5-pro` · `gemini-2.5-flash-lite` |
| **OpenAI** | `gpt-5.4-mini` ★ · `gpt-5.5` · `gpt-5.5-2026-04-23` · `gpt-5.4` · `gpt-5.4-nano` · `o4-mini` · `o3` · `gpt-4.1` · `gpt-4o` |
| **Anthropic** | `claude-sonnet-4-6` ★ · `claude-opus-4-8` · `claude-haiku-4-5-20251001` · `claude-opus-4-7` |
| **Groq** | `llama-3.3-70b-versatile` ★ · `llama-3.1-8b-instant` |
| **Ollama** | `llama3.3` ★ · `llama3.1` · `qwen2.5-coder` · `deepseek-coder-v2` · `mistral-nemo` |

(★ = recommended default for the provider; † = Gemini 3.x is on the Developer API now; Vertex AI rollout is still region-gated as of 2026-05-27)

Run `oscar providers` for the live, color-coded version of this table with API-key status indicators.

### VS Code Extension

```bash
cd vscode-oscar
npm install
npm run compile
# Press F5 in VS Code to launch the Extension Development Host
```

The extension shows the active LLM in the status bar. Click it (or run **OSCAR: Select LLM provider and model** from the Command Palette) to pick a different one — the chosen env vars are copied to your clipboard, ready to paste into `.env`.

## Usage

### CLI

```bash
oscar                  # Start interactive session
oscar --debug          # Debug mode
oscar --dry-run        # Dry run (no destructive ops)
oscar --config-check   # Verify configuration
```

Inside the prompt:

```
OSCAR> providers           # List all supported providers and models
OSCAR> config              # Show current provider/model + tool count
OSCAR> test                # Round-trip the current LLM
OSCAR> git status
OSCAR> compare main and feature-branch
OSCAR> review feature-branch against main
OSCAR> search for Python async best practices
OSCAR> navigate to https://docs.python.org
```

### API

```bash
oscar-server                                          # Start FastAPI on port 8420
curl http://127.0.0.1:8420/providers | jq            # Inspect the live model catalog
curl -X POST http://127.0.0.1:8420/chat \
     -H 'Content-Type: application/json' \
     -d '{"message":"show me git status"}'
```

## Project Structure

```
src/oscar/
├── api/server.py               # FastAPI endpoints incl. /providers
├── cli/main.py                 # CLI with `providers`, `config`, `test`
├── config/
│   ├── providers.py            # 5-provider / 21-model catalog (single source of truth)
│   ├── prompts.py              # System prompt
│   └── settings.py             # Env-driven settings, API-key resolution
├── core/
│   ├── agent.py                # Asterix agent orchestrator
│   ├── asterix_patch.py        # Multi-provider LLM bridge (Gemini/OpenAI/Claude/Groq/Ollama)
│   ├── safety.py               # Human-in-the-loop safety callbacks
│   └── repo_context.py         # Active-repo handling
└── tools/
    ├── git_tool.py             # Git operations (9 functions)
    ├── shell.py                # Shell command execution
    ├── web_search.py           # Tavily web search
    └── browser.py              # Playwright browser automation
```

## Built With

- **[Asterix](https://github.com/adityasarade/asterix)** — Agentic framework (ReAct loop, memory, tool management)
- **Gemini · OpenAI · Anthropic · Groq · Ollama** — pluggable LLM providers
- **`google-genai` · `openai` · `anthropic` · `ollama`** — official Python SDKs
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
