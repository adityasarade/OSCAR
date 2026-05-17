from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from oscar.api import server
from oscar.api.runtime import clear_active_broker


@pytest.fixture
def fake_agent():
    agent = Mock()
    agent.chat.return_value = "ok"
    agent.conversation_history = []
    agent.blocks = {"session_context": SimpleNamespace(content="")}
    agent.get_all_tools.return_value = [SimpleNamespace(name="git_status")]
    agent.id = "oscar-test"
    return agent


@pytest.fixture
def client(monkeypatch, fake_agent):
    executor = ThreadPoolExecutor(max_workers=1)
    clear_active_broker()
    monkeypatch.setattr(server, "_agent", fake_agent)
    monkeypatch.setattr(server, "_chat_executor", executor)
    test_client = TestClient(server.app)
    try:
        yield test_client
    finally:
        clear_active_broker()
        executor.shutdown(wait=False, cancel_futures=True)
