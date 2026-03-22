"""
OSCAR Agent — Asterix-powered GitHub coding assistant.

Creates an Asterix Agent with Gemini 2.5 Flash via Vertex AI, registers all
OSCAR tools, and patches in safety/audit/progress callbacks.

Usage:
    from oscar.core.agent import get_agent
    response = get_agent().chat("compare main and dev")
"""

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from rich.console import Console

# Apply Asterix patches (idempotent — adds Gemini/Vertex AI support)
import oscar.core.asterix_patch  # noqa: F401

from asterix import Agent, BlockConfig

from oscar.config.prompts import SYSTEM_PROMPT
from oscar.core.safety import on_before_tool_call
from oscar.config.settings import settings

# Tool imports
from oscar.tools.git_tool import (
    git_status, git_compare, git_review, git_log,
    git_diff, git_branches, git_checkout, git_commit, git_push,
)
from oscar.tools.shell import run_shell_command
from oscar.tools.web_search import web_search
from oscar.tools.browser import (
    browser_navigate, browser_search, browser_extract, browser_download,
)

console = Console()

# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

_audit_path = settings.data_dir / "logs" / "audit.jsonl"
_audit_path.parent.mkdir(parents=True, exist_ok=True)


def _audit_log(tool_name: str, arguments: dict) -> None:
    """Append tool call to JSONL audit trail."""
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "arguments": {k: str(v)[:200] for k, v in arguments.items()},
        }
        with open(_audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Step progress tracking (consumed by FastAPI streaming)
# ---------------------------------------------------------------------------

_last_step: Dict[str, Any] = {}


def _on_step(step_info: dict) -> None:
    """Store latest heartbeat step info."""
    global _last_step
    _last_step = step_info


def get_last_step() -> Dict[str, Any]:
    """Return the most recent step info (for API streaming)."""
    return _last_step


# ---------------------------------------------------------------------------
# Monkey-patch Asterix Agent to support custom system prompt + callbacks
# ---------------------------------------------------------------------------

def _patch_agent(agent: Agent, system_prompt: str) -> None:
    """Patch an Asterix v0.2.1 Agent with OSCAR-specific features.

    Asterix v0.2.1 has Gemini support but doesn't yet have constructor
    params for system_prompt, on_before_tool_call, on_after_tool_call,
    or on_step. We set these up by patching instance methods.
    """

    # --- Custom system prompt ------------------------------------------------
    original_build = agent._build_system_prompt

    def patched_build_system_prompt() -> str:
        """Replace generic prompt with OSCAR's GitHub-focused prompt."""
        # Start with our custom prompt
        lines = [system_prompt, ""]

        # Append memory blocks (reuse original logic for block formatting)
        lines.append("# Memory Blocks")
        for block_name, block in agent.blocks.items():
            lines.append(f"## {block_name}")
            if block.config.description:
                lines.append(f"*{block.config.description}*")
            lines.append("```")
            lines.append(block.content if block.content else "(empty)")
            lines.append("```")
            lines.append("")

        # Tool usage instructions
        lines.extend([
            "# Tool Calling",
            "You have access to function calling tools. When a tool is relevant:",
            "- **Call the tool using function calling** — do not just describe what it would return.",
            "- Use memory tools to persist important information across sessions.",
            "",
        ])
        return "\n".join(lines)

    agent._build_system_prompt = patched_build_system_prompt

    # --- on_before_tool_call (safety confirmation) ---------------------------
    original_execute = agent._execute_tool_calls

    def patched_execute_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Wrap tool execution with safety check and audit logging."""
        results = []
        for tc in tool_calls:
            tool_id = tc["id"]
            tool_name = tc["name"]

            try:
                arguments = json.loads(tc["arguments"])
            except (json.JSONDecodeError, TypeError):
                arguments = {}

            # Safety gate
            approved = on_before_tool_call(tool_name, arguments)
            if not approved:
                console.print(f"[yellow]  Rejected: {tool_name}[/yellow]")
                results.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": "Tool execution was rejected by user.",
                })
                _audit_log(tool_name, {"_status": "rejected", **arguments})
                continue

            # Execute via original registry
            try:
                tool_result = agent._tool_registry.execute_tool(tool_name, **arguments)
                console.print(f"[green]  Done: {tool_name}[/green]")

                results.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": str(tool_result),
                })
            except Exception as e:
                console.print(f"[red]  Error: {tool_name} — {e}[/red]")
                results.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": f"Error: {e}",
                })

            # Audit log
            _audit_log(tool_name, arguments)

        return results

    agent._execute_tool_calls = patched_execute_tool_calls


# ---------------------------------------------------------------------------
# Agent singleton
# ---------------------------------------------------------------------------

_agent_instance = None


def _create_agent() -> Agent:
    """Create and configure the OSCAR Asterix agent."""
    prompt = SYSTEM_PROMPT.format(
        os_info=platform.platform(),
        working_directory=str(Path.cwd()),
    )

    agent = Agent(
        agent_id="oscar",
        model="gemini/gemini-2.5-flash",
        blocks={
            "session_context": BlockConfig(
                size=4000, priority=1,
                description="Recent interactions and task context",
            ),
            "knowledge_base": BlockConfig(
                size=3000, priority=2,
                description="Facts and information from searches",
            ),
            "user_preferences": BlockConfig(
                size=1000, priority=3,
                description="Learned user preferences and patterns",
            ),
        },
        max_tokens=4096,
    )

    # Patch in OSCAR features (system prompt, safety, audit)
    _patch_agent(agent, prompt)

    # -- Register git tools ---------------------------------------------------
    agent.tool(name="git_status", description="Show repository status, current branch, and working tree state")(git_status)
    agent.tool(name="git_compare", description="Compare two branches: commit count, changed files, diff summary, and commit log")(git_compare)
    agent.tool(name="git_review", description="Full diff of a branch for code review, with diffstat summary")(git_review)
    agent.tool(name="git_log", description="Show formatted commit history for a branch")(git_log)
    agent.tool(name="git_diff", description="Show diff for a specific file")(git_diff)
    agent.tool(name="git_branches", description="List all local and remote branches")(git_branches)
    agent.tool(name="git_checkout", description="Switch to a different branch")(git_checkout)
    agent.tool(name="git_commit", description="Commit staged changes with a message")(git_commit)
    agent.tool(name="git_push", description="Push commits to a remote repository")(git_push)

    # -- Register shell tool --------------------------------------------------
    agent.tool(name="run_shell_command", description="Execute a shell command with safety validation and cross-platform support")(run_shell_command)

    # -- Register web search tool ---------------------------------------------
    agent.tool(name="web_search", description="Search the web for documentation, errors, or external information")(web_search)

    # -- Register browser tools -----------------------------------------------
    agent.tool(name="browser_navigate", description="Navigate to a URL and return page content")(browser_navigate)
    agent.tool(name="browser_search", description="Perform a Google search via browser and return results")(browser_search)
    agent.tool(name="browser_extract", description="Extract content from the currently loaded page")(browser_extract)
    agent.tool(name="browser_download", description="Download a file from a URL")(browser_download)

    tool_count = len(agent.get_all_tools())
    console.print(f"[dim]OSCAR agent initialized — {tool_count} tools (Asterix + Gemini 2.5 Flash via Vertex AI)[/dim]")
    return agent


def get_agent() -> Agent:
    """Return the singleton OSCAR agent, creating it on first call."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = _create_agent()
    return _agent_instance
