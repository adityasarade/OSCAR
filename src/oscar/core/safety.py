"""
OSCAR Safety Callback — on_before_tool_call for Asterix agent.

Assesses tool call risk and prompts for user confirmation when needed.
Low risk auto-approves; medium/high prompt yes/no; dangerous requires typing CONFIRM.
"""

import re
from rich.console import Console
from rich.prompt import Confirm, Prompt

from oscar.config.settings import SAFETY_PATTERNS

console = Console()

# Risk priority for comparisons
_RISK_PRIORITY = {"low": 0, "medium": 1, "high": 2, "dangerous": 3}

# Tools that are inherently medium risk regardless of arguments
_MEDIUM_RISK_TOOLS = {"git_push", "git_checkout", "git_commit"}


def _extract_strings(obj) -> str:
    """Recursively extract all string values from a nested structure."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_extract_strings(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_extract_strings(v) for v in obj)
    return str(obj)


def _summarize_args(arguments: dict) -> str:
    """Produce a short human-readable summary of tool arguments."""
    parts = []
    for key, value in arguments.items():
        display = str(value)
        if len(display) > 60:
            display = display[:57] + "..."
        parts.append(f'{key}="{display}"')
    summary = ", ".join(parts)
    if len(summary) > 120:
        summary = summary[:117] + "..."
    return summary


def _assess_risk(tool_name: str, check_string: str) -> str:
    """Assess the risk level of a tool call.

    Returns: "low", "medium", "high", or "dangerous"
    """
    # Start with tool-name-based default
    if tool_name in _MEDIUM_RISK_TOOLS:
        risk = "medium"
    else:
        risk = "low"

    # Only apply pattern checks for shell commands or medium+ tools
    if tool_name == "run_shell_command" or risk != "low":
        # Check dangerous command regexes (highest priority — return immediately)
        for pattern in SAFETY_PATTERNS["dangerous_commands"]:
            if re.search(pattern, check_string, re.IGNORECASE):
                return "dangerous"

        # Check high risk keywords
        check_lower = check_string.lower()
        for keyword in SAFETY_PATTERNS["high_risk_keywords"]:
            if keyword in check_lower:
                if _RISK_PRIORITY["high"] > _RISK_PRIORITY[risk]:
                    risk = "high"

        # Check medium risk keywords
        for keyword in SAFETY_PATTERNS["medium_risk_keywords"]:
            if keyword in check_lower:
                if _RISK_PRIORITY["medium"] > _RISK_PRIORITY[risk]:
                    risk = "medium"

    return risk


def on_before_tool_call(tool_name: str, arguments: dict) -> bool:
    """Asterix on_before_tool_call callback.

    Assesses tool call risk and prompts the user for confirmation when needed.

    Args:
        tool_name: Name of the tool being called.
        arguments: Dictionary of arguments passed to the tool.

    Returns:
        True to allow the tool call, False to reject it.
    """
    check_string = tool_name + " " + _extract_strings(arguments)
    risk = _assess_risk(tool_name, check_string)
    summary = _summarize_args(arguments)

    if risk == "low":
        return True

    if risk == "medium":
        return Confirm.ask(
            f"[yellow]Warning — Medium risk:[/yellow] {tool_name}({summary}). Allow?",
            default=False,
        )

    if risk == "high":
        return Confirm.ask(
            f"[bold orange3]Warning — High risk:[/bold orange3] {tool_name}({summary}). Allow?",
            default=False,
        )

    # dangerous
    response = Prompt.ask(
        f"[bold red]DANGEROUS:[/bold red] {tool_name}({summary}). Type CONFIRM to proceed",
        default="",
    )
    return response == "CONFIRM"
