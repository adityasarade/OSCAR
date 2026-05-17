"""
OSCAR Git Tool — GitHub-specialized git operations as standalone functions.

Each function uses subprocess.run with list args (no shell=True) to avoid
injection. Large outputs are truncated at 50K characters.
"""

import subprocess
import logging
from typing import Any, Dict, List


_TRUNCATE_LIMIT = 50_000
logger = logging.getLogger(__name__)


def _truncate(text: str, limit: int = _TRUNCATE_LIMIT) -> str:
    """Truncate text and append a notice if it exceeds the limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[...truncated at 50K chars]"


def _run_git(args: List[str]) -> str:
    """Run a git command and return stdout or a formatted error string."""
    logger.debug("Running git command: git %s", " ".join(args))
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or f"git command failed with exit code {result.returncode}"
        logger.warning("Git command failed: git %s: %s", " ".join(args), error)
        return f"Error: {error}"
    return result.stdout.strip()


def _git_error(result: subprocess.CompletedProcess) -> str:
    """Return the public error string for a failed git subprocess."""
    error = result.stderr.strip() or f"git command failed with exit code {result.returncode}"
    return f"Error: {error}"


def _parse_porcelain_v2(output: str) -> Dict[str, Any]:
    """Parse `git status --porcelain=v2 --branch` output."""
    parsed: Dict[str, Any] = {
        "branch": "",
        "upstream": "",
        "ahead": 0,
        "behind": 0,
        "changes": [],
    }

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# "):
            fields = line[2:].split()
            if not fields:
                continue
            key = fields[0]
            if key == "branch.head" and len(fields) > 1:
                parsed["branch"] = fields[1]
            elif key == "branch.upstream" and len(fields) > 1:
                parsed["upstream"] = fields[1]
            elif key == "branch.ab" and len(fields) > 2:
                parsed["ahead"] = int(fields[1].lstrip("+"))
                parsed["behind"] = int(fields[2].lstrip("-"))
            continue

        if line.startswith("? "):
            parsed["changes"].append({"status": "??", "path": line[2:]})
            continue

        if line.startswith("! "):
            parsed["changes"].append({"status": "!!", "path": line[2:]})
            continue

        if line.startswith("1 "):
            fields = line.split(" ", 8)
            if len(fields) == 9:
                parsed["changes"].append({"status": fields[1], "path": fields[8]})
            continue

        if line.startswith("2 "):
            fields = line.split(" ", 9)
            if len(fields) == 10:
                path = fields[9].split("\t", 1)[0]
                parsed["changes"].append({"status": fields[1], "path": path})
            continue

        if line.startswith("u "):
            fields = line.split(" ", 10)
            if len(fields) == 11:
                parsed["changes"].append({"status": fields[1], "path": fields[10]})

    return parsed


def _format_parsed_status(parsed: Dict[str, Any]) -> str:
    """Build OSCAR's public git status string from parsed porcelain data."""
    branch = parsed["branch"] or "(unknown)"
    parts = [f"Branch: {branch}"]

    if parsed["upstream"]:
        parts.append(f"Upstream: {parsed['upstream']}")

    ahead = parsed["ahead"]
    behind = parsed["behind"]
    if ahead or behind:
        parts.append(f"Ahead: {ahead} Behind: {behind}")

    parts.append("")
    if not parsed["changes"]:
        parts.append("Working tree clean.")
    else:
        parts.append("Changes:")
        for change in parsed["changes"]:
            parts.append(f"{change['status']} {change['path']}")

    return "\n".join(parts)


def git_status() -> str:
    """Get the current repository status including branch name, repo root, and working tree state."""
    command = ["git", "status", "--porcelain=v2", "--branch"]
    logger.debug("Running git command: %s", " ".join(command))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = _git_error(result)
        logger.warning("Git status failed: %s", error)
        return error

    return _truncate(_format_parsed_status(_parse_porcelain_v2(result.stdout)))


def git_compare(base: str, head: str) -> str:
    """Compare two branches showing commit count, changed files, and commit log.

    Args:
        base: The base branch (e.g. 'main').
        head: The head branch to compare against base.
    """
    commit_count = _run_git(["rev-list", "--count", f"{base}...{head}"])
    diffstat = _run_git(["diff", "--stat", f"{base}...{head}"])
    log = _run_git(["log", "--oneline", f"{base}...{head}"])

    parts = [
        f"Comparing {base} ↔ {head}",
        f"Commits: {commit_count}",
        "",
        "Changed files:",
        diffstat,
        "",
        "Commit log:",
        log,
    ]
    return _truncate("\n".join(parts))


def git_review(branch: str, base: str = "main") -> str:
    """Get the full diff of a branch against base for code review.

    Args:
        branch: The branch to review.
        base: The base branch to diff against (default: 'main').
    """
    diffstat = _run_git(["diff", "--stat", f"{base}...{branch}"])
    diff = _run_git(["diff", f"{base}...{branch}"])

    parts = [
        f"Review: {branch} vs {base}",
        "",
        "Diffstat:",
        diffstat,
        "",
        "Full diff:",
        diff,
    ]
    return _truncate("\n".join(parts))


def git_log(branch: str = "HEAD", count: int = 10) -> str:
    """Show formatted commit history.

    Args:
        branch: Branch or ref to show history for (default: 'HEAD').
        count: Number of commits to show (default: 10).
    """
    return _run_git(["log", "--oneline", "--graph", "-n", str(count), branch])


def git_diff(file_path: str, staged: bool = False) -> str:
    """Show the diff for a specific file.

    Args:
        file_path: Path to the file to diff.
        staged: If True, show staged (cached) changes instead of unstaged.
    """
    args = ["diff"]
    if staged:
        args.append("--cached")
    args.extend(["--", file_path])

    return _truncate(_run_git(args))


def git_branches() -> str:
    """List all local and remote branches."""
    command = [
        "git",
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads/",
        "refs/remotes/origin/",
    ]
    logger.debug("Running git command: %s", " ".join(command))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = _git_error(result)
        logger.warning("Git branch listing failed: %s", error)
        return error

    branches = []
    for raw_line in result.stdout.splitlines():
        branch = raw_line.strip()
        if not branch or branch == "origin/HEAD":
            continue
        if branch.startswith("origin/"):
            branch = f"remotes/{branch}"
        if branch not in branches:
            branches.append(branch)

    return "\n".join(branches)


def git_checkout(branch: str) -> str:
    """Switch to a different branch.

    Args:
        branch: The branch name to check out.
    """
    return _run_git(["checkout", branch])


def git_commit(message: str) -> str:
    """Commit currently staged changes with the given message.

    Args:
        message: The commit message.
    """
    return _run_git(["commit", "-m", message])


def git_push(remote: str = "origin", branch: str = "") -> str:
    """Push commits to a remote repository.

    Args:
        remote: Remote name (default: 'origin').
        branch: Branch to push. If empty, pushes the current branch.
    """
    args = ["push", remote]
    if branch:
        args.append(branch)
    return _run_git(args)
