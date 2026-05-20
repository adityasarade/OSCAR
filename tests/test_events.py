from oscar.core import events


def test_emit_delivers_to_listener():
    received = []

    unsub = events.subscribe(received.append)
    try:
        events.emit({"type": "tool_call", "tool_name": "git_status", "data": ""})
        events.emit({"type": "tool_result", "data": "ok"})
    finally:
        unsub()

    assert [e["type"] for e in received] == ["tool_call", "tool_result"]


def test_unsubscribe_stops_delivery():
    received = []
    unsub = events.subscribe(received.append)
    unsub()

    events.emit({"type": "step", "data": "after-unsub"})
    assert received == []


def test_listener_exception_does_not_block_others():
    received = []

    def boom(_evt):
        raise RuntimeError("listener failure")

    unsub1 = events.subscribe(boom)
    unsub2 = events.subscribe(received.append)
    try:
        events.emit({"type": "step", "data": "x"})
    finally:
        unsub1()
        unsub2()

    assert received == [{"type": "step", "data": "x"}]
