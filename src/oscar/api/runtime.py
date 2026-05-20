"""Runtime coordination primitives for API chat streams."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Dict, Optional

from oscar.core import events


class ChatBroker:
    """Bridge worker-thread agent execution with the FastAPI event loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.events: asyncio.Queue = asyncio.Queue()
        self.pending_confirms: dict[str, tuple[threading.Event, list[bool]]] = {}
        self.cancel_flag = threading.Event()
        self.loop = loop
        self._confirm_lock = threading.Lock()
        self._unsubscribe: Optional[Callable[[], None]] = None

    def _ensure_confirm(self, request_id: str) -> tuple[threading.Event, list[bool]]:
        with self._confirm_lock:
            return self.pending_confirms.setdefault(
                request_id,
                (threading.Event(), [False]),
            )

    def emit(self, event_dict: dict) -> None:
        """Publish an SSE event from any thread."""
        if event_dict.get("type") == "confirm":
            data = event_dict.get("data") or {}
            request_id = data.get("request_id")
            if request_id:
                self._ensure_confirm(str(request_id))
        self.loop.call_soon_threadsafe(self.events.put_nowait, event_dict)

    def attach(self) -> None:
        """Subscribe to global agent events so they're forwarded as SSE."""
        if self._unsubscribe is not None:
            return

        def _listener(event: Dict[str, Any]) -> None:
            self.emit(event)

        self._unsubscribe = events.subscribe(_listener)

    def detach(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def wait_for_confirm(self, request_id: str, timeout: int = 300) -> bool:
        """Wait for a user confirmation, defaulting to rejection on timeout."""
        event, result = self._ensure_confirm(request_id)
        try:
            if not event.wait(timeout):
                return False
            return bool(result[0])
        finally:
            with self._confirm_lock:
                self.pending_confirms.pop(request_id, None)

    def set_confirm(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending confirmation. Returns False for unknown IDs."""
        with self._confirm_lock:
            pending = self.pending_confirms.get(request_id)
            if pending is None:
                return False
            event, result = pending
            result[0] = approved
            event.set()
            return True

    def cancel(self) -> None:
        """Request cancellation and unblock any pending confirmation."""
        self.cancel_flag.set()
        with self._confirm_lock:
            pending = list(self.pending_confirms.values())
        for event, result in pending:
            result[0] = False
            event.set()

    def is_cancelled(self) -> bool:
        return self.cancel_flag.is_set()


_active_broker: Optional[ChatBroker] = None
_active_broker_lock = threading.Lock()


def get_active_broker() -> Optional[ChatBroker]:
    with _active_broker_lock:
        return _active_broker


def set_active_broker(broker: ChatBroker) -> None:
    global _active_broker
    with _active_broker_lock:
        _active_broker = broker


def clear_active_broker() -> None:
    global _active_broker
    with _active_broker_lock:
        _active_broker = None
