from oscar.api import server


def test_health_returns_ok_and_version(client, monkeypatch):
    monkeypatch.setattr(server, "git_status", lambda: "Branch: main")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_history_returns_role_content_dicts(client, fake_agent):
    fake_agent.conversation_history = [{"role": "user", "content": "hi"}]

    response = client.get("/history")

    assert response.status_code == 200
    assert response.json() == [{"role": "user", "content": "hi", "timestamp": None}]


def test_status_returns_agent_metadata(client, fake_agent):
    fake_agent.conversation_history = [{"role": "user", "content": "hi"}]

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json() == {
        "agent_id": "oscar-test",
        "tools": ["git_status"],
        "memory_blocks": ["session_context"],
        "conversation_length": 1,
    }


def test_branches_parses_git_branch_output(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "git_branches",
        lambda: "\n".join(
            [
                "* main",
                "  feature/api",
                "  remotes/origin/main",
                "  remotes/origin/feature/api",
                "  remotes/origin/HEAD -> origin/main",
            ]
        ),
    )

    response = client.get("/branches")

    assert response.status_code == 200
    assert response.json() == {
        "branches": ["main", "feature/api"],
        "current": "main",
    }


def test_cancel_without_active_chat_returns_conflict(client):
    response = client.post("/chat/cancel", json={})

    assert response.status_code == 409


def test_confirm_unknown_id_returns_not_found(client):
    response = client.post(
        "/chat/confirm",
        json={"request_id": "missing", "approved": True},
    )

    assert response.status_code == 404
