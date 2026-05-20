"""Active-repo context for OSCAR git/shell operations.

The active repo is **thread-local** so HTTP endpoints handling concurrent
requests can't clobber the chat worker thread's view of the repo. Each
thread has its own active repo:

  - Event-loop thread: set transiently by ``use_repo(...)`` inside an HTTP
    handler so /branches /compare /review honour the request's ``repo_path``.
  - Chat executor thread: set by ``/chat/stream`` for the duration of the
    chat so every tool call sees the same repo.
  - CLI main thread: set once at startup from ``--repo``/cwd.

Endpoints that take an explicit ``repo_path`` override the thread-local
for the duration of the call via ``use_repo``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


logger = logging.getLogger(__name__)

_state = threading.local()


def _normalize(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        resolved = Path(path).expanduser().resolve()
    except Exception:
        return None
    if not resolved.exists() or not resolved.is_dir():
        return None
    return str(resolved)


def _get() -> Optional[str]:
    return getattr(_state, "active_repo", None)


def _set(value: Optional[str]) -> None:
    _state.active_repo = value


def set_active_repo(path: Optional[str]) -> Optional[str]:
    """Set (or clear, with None/empty) the current thread's active repo."""
    normalized = _normalize(path)
    _set(normalized)
    if normalized:
        logger.info("Active repo set to %s", normalized)
    else:
        logger.info("Active repo cleared")
    return normalized


def get_active_repo() -> Optional[str]:
    return _get()


def resolve_cwd(cwd: Optional[str] = None) -> Optional[str]:
    """Return the cwd to use for a subprocess: explicit > active > None."""
    explicit = _normalize(cwd)
    if explicit:
        return explicit
    return _get()


@contextmanager
def use_repo(path: Optional[str]) -> Iterator[Optional[str]]:
    """Temporarily override the current thread's active repo.

    Passing ``None`` keeps the existing value (useful for endpoints where
    repo_path is optional and we want them to fall through to the
    caller's prior selection).
    """
    normalized = _normalize(path)
    previous = _get()
    if normalized is not None:
        _set(normalized)
    try:
        yield normalized or previous
    finally:
        _set(previous)


def is_git_repo(path: Optional[str] = None) -> bool:
    """Return True if `path` (or active repo, or cwd) is inside a git work tree."""
    cwd = resolve_cwd(path) or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"
