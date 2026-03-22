"""
OSCAR Shell Tool — Cross-platform command execution with safety checks.

Standalone function that keeps the safe-commands allowlist, SAFETY_PATTERNS
regex checks, and cross-platform translation from the original ShellTool class.
"""

import subprocess
import shlex
import re
import platform

from oscar.config.settings import SAFETY_PATTERNS


_IS_WINDOWS = platform.system() == "Windows"

SAFE_COMMANDS = {
    "ls", "dir", "pwd", "cd", "mkdir", "echo", "cat", "type",
    "python", "pip", "git", "node", "npm", "curl", "wget",
    "tree", "whoami", "date", "which", "where",
}

_COMMAND_TRANSLATIONS = {
    "ls": "dir" if _IS_WINDOWS else "ls",
    "pwd": "cd" if _IS_WINDOWS else "pwd",
    "cat": "type" if _IS_WINDOWS else "cat",
    "which": "where" if _IS_WINDOWS else "which",
}


def _validate_command(command: str) -> str | None:
    """Return an error message if the command is unsafe, or None if OK."""
    command_lower = command.lower().strip()

    for pattern in SAFETY_PATTERNS["dangerous_commands"]:
        if re.search(pattern, command, re.IGNORECASE):
            return "Dangerous pattern detected"

    base_command = command_lower.split()[0] if command_lower.split() else ""

    if base_command in SAFE_COMMANDS:
        return None

    for keyword in SAFETY_PATTERNS["high_risk_keywords"]:
        if keyword in command_lower:
            return f"High-risk operation detected: {keyword}"

    return None


def _translate_command(command: str) -> str:
    """Translate command for the current platform."""
    parts = command.split()
    if not parts:
        return command

    base = parts[0].lower()
    if base in _COMMAND_TRANSLATIONS:
        return command.replace(parts[0], _COMMAND_TRANSLATIONS[base], 1)

    return command


def run_shell_command(command: str, cwd: str = "", timeout: int = 30) -> str:
    """Execute a shell command with safety validation and cross-platform support.

    Args:
        command: The shell command to execute.
        cwd: Working directory for the command. Uses current directory if empty.
        timeout: Maximum seconds to wait before killing the process (default: 30).

    Returns:
        Command stdout on success, or an error string on failure.
    """
    error = _validate_command(command)
    if error:
        return f"Error: Command blocked — {error}"

    translated = _translate_command(command)
    run_cwd = cwd if cwd else None

    try:
        if _IS_WINDOWS:
            result = subprocess.run(
                translated,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=run_cwd,
            )
        else:
            args = shlex.split(translated)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=run_cwd,
            )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                return f"Error: {stderr}"
            return f"Error: Command exited with code {result.returncode}"

        return result.stdout.strip() if result.stdout else "Command executed successfully"

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error: {e}"
