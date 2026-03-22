# OSCAR — GitHub Coding Assistant for VS Code

AI-powered sidebar assistant for GitHub repository operations. Compare branches, review PRs, analyze diffs, and run commands — all through natural language.

## Features

- **Branch comparison** — compare any two branches with LLM-summarized diffs
- **Code review** — get PR-style feedback on branch changes
- **Git operations** — status, log, diff, checkout, commit, push via natural language
- **Shell commands** — run tests, builds, and scripts with safety confirmation
- **Web search** — look up documentation and error messages
- **Persistent memory** — remembers context across sessions

## Getting Started

1. Install the extension
2. Start the OSCAR backend server:
   ```bash
   pip install oscar-agent
   oscar-server
   ```
3. Click the OSCAR icon in the VS Code activity bar
4. Start typing queries in the sidebar chat

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `oscar.serverUrl` | `http://127.0.0.1:8420` | URL of the OSCAR backend server |

## Example Queries

- "Show me the git status"
- "Compare main and feature-branch"
- "Review the changes on dev vs main"
- "What changed in the last 5 commits?"
- "Run the test suite"
- "Search for Python async best practices"

## Architecture

OSCAR uses the [Asterix](https://github.com/adityasarade/Asterix) agentic framework with Gemini 2.5 Flash (Vertex AI) for intelligent tool routing. The extension communicates with a FastAPI backend that wraps the Asterix agent.

## Safety

Destructive operations (git push, dangerous shell commands) require explicit user confirmation before execution. All tool calls are logged to an audit trail.

## License

MIT
