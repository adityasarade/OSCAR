"""Lightweight event bus for OSCAR agent progress.

Both the SSE chat broker and the CLI subscribe here. The agent emits a
small set of event types — `step`, `thinking`, `tool_call`, `tool_result`,
`confirm`, `response`, `error`, `done`, `cancelled` — and listeners decide
how to render them.

This is intentionally simple: no async, no priorities, no buffering.
Listeners must not block; they should hand off heavy work themselves.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List


logger = logging.getLogger(__name__)

Listener = Callable[[Dict[str, Any]], None]

_lock = threading.Lock()
_listeners: List[Listener] = []


def subscribe(listener: Listener) -> Callable[[], None]:
    """Register a listener. Returns an unsubscribe callable."""
    with _lock:
        _listeners.append(listener)

    def _unsubscribe() -> None:
        with _lock:
            try:
                _listeners.remove(listener)
            except ValueError:
                pass

    return _unsubscribe


def emit(event: Dict[str, Any]) -> None:
    """Dispatch an event to all listeners. Failures in one don't affect others."""
    with _lock:
        snapshot = list(_listeners)
    for listener in snapshot:
        try:
            listener(event)
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("Event listener raised: %s", exc)
