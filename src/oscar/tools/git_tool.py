"""
OSCAR Git Tool — GitHub-specialized git operations as standalone functions.

Each function uses subprocess.run with list args (no shell=True) to avoid
injection. Large outputs are truncated at 50K characters.
"""

import subprocess
from typing import List


_TRUNCATE_LIMIT = 50_000


def _truncate(text: str, limit: int = _TRUNCATE_LIMIT) -> str:
    """Truncate text and append a notice if it exceeds the limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[...truncated at 50K chars]"


def _run_git(args: List[str]) -> str:
    """Run a git command and return stdout or a formatted error string."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or f"git command failed with exit code {result.returncode}"
        return f"Error: {error}"
    return result.stdout.strip()


def git_status() -> str:
    """Get the current repository status including branch name, repo root, and working tree state."""
    repo_root = _run_git(["rev-parse", "--show-toplevel"])
    branch = _run_git(["branch", "--show-current"])
    status = _run_git(["status"])

    return f"Repository: {repo_root}\nBranch: {branch}\n\n{status}"


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
    return _run_git(["branch", "-a"])


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
