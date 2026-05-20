from pathlib import Path

import pytest

from oscar.core import repo_context


@pytest.fixture(autouse=True)
def _reset_active_repo():
    """Don't leak state between tests."""
    previous = repo_context.get_active_repo()
    repo_context.set_active_repo(None)
    try:
        yield
    finally:
        repo_context.set_active_repo(previous)


def test_set_and_get_active_repo_resolves_path(tmp_path):
    resolved = repo_context.set_active_repo(str(tmp_path))
    assert resolved == str(tmp_path.resolve())
    assert repo_context.get_active_repo() == str(tmp_path.resolve())


def test_set_active_repo_rejects_missing_path(tmp_path):
    bogus = tmp_path / "does-not-exist"
    assert repo_context.set_active_repo(str(bogus)) is None
    assert repo_context.get_active_repo() is None


def test_set_active_repo_rejects_file(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("hi")
    assert repo_context.set_active_repo(str(f)) is None


def test_set_active_repo_with_none_clears(tmp_path):
    repo_context.set_active_repo(str(tmp_path))
    repo_context.set_active_repo(None)
    assert repo_context.get_active_repo() is None


def test_resolve_cwd_prefers_explicit(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    repo_context.set_active_repo(str(tmp_path))

    assert repo_context.resolve_cwd(str(other)) == str(other.resolve())
    # Still falls back to active repo when explicit is missing.
    assert repo_context.resolve_cwd(None) == str(tmp_path.resolve())


def test_use_repo_restores_previous_value(tmp_path):
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"
    outer.mkdir()
    inner.mkdir()

    repo_context.set_active_repo(str(outer))
    with repo_context.use_repo(str(inner)) as active:
        assert active == str(inner.resolve())
        assert repo_context.get_active_repo() == str(inner.resolve())

    assert repo_context.get_active_repo() == str(outer.resolve())


def test_use_repo_with_none_keeps_previous(tmp_path):
    repo_context.set_active_repo(str(tmp_path))
    with repo_context.use_repo(None):
        assert repo_context.get_active_repo() == str(tmp_path.resolve())
    assert repo_context.get_active_repo() == str(tmp_path.resolve())


def test_active_repo_is_thread_local(tmp_path):
    """Threads must not see each other's active_repo — racing HTTP requests
    must not clobber the chat worker thread's view."""
    import threading
    import time

    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()

    repo_context.set_active_repo(str(repo_a))
    other_seen = {}
    barrier = threading.Barrier(2)

    def other_thread():
        # Other thread starts with no active repo.
        other_seen["initial"] = repo_context.get_active_repo()
        barrier.wait()
        # Set its own repo and verify main thread is unaffected.
        repo_context.set_active_repo(str(repo_b))
        other_seen["own"] = repo_context.get_active_repo()
        barrier.wait()
        # Hold long enough for main thread to read its local while we
        # have a different value set.
        time.sleep(0.05)

    t = threading.Thread(target=other_thread)
    t.start()
    barrier.wait()
    # Main thread still sees repo_a even though the other thread is
    # about to set repo_b.
    assert repo_context.get_active_repo() == str(repo_a.resolve())
    barrier.wait()
    # Even after the other thread sets repo_b, main thread is unaffected.
    assert repo_context.get_active_repo() == str(repo_a.resolve())
    t.join()
    assert other_seen["initial"] is None
    assert other_seen["own"] == str(repo_b.resolve())
