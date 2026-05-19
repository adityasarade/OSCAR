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


def test_metrics_returns_llm_and_audit_sections(client, monkeypatch, tmp_path):
    audit_file = tmp_path / "audit.jsonl"
    audit_file.write_text(
        '\n'.join(
            [
                '{"timestamp": "t", "tool": "git_status", "risk": "low", "approved": true, "latency_ms": 12.5}',
                '{"timestamp": "t", "tool": "git_push", "risk": "medium", "approved": false}',
            ]
        ),
        encoding="utf-8",
    )

    from oscar.core import metrics as metrics_mod

    monkeypatch.setattr(metrics_mod, "audit_path", lambda: audit_file)
    monkeypatch.setattr(metrics_mod, "llm_performance", lambda: {"providers": {}})

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["llm"] == {"providers": {}}
    audit = body["audit"]
    assert audit["entries"] == 2
    assert audit["approved"] == 1
    assert audit["rejected"] == 1
    assert audit["by_tool"] == {"git_status": 1, "git_push": 1}
    assert audit["by_risk"]["low"] == 1
    assert audit["by_risk"]["medium"] == 1
    assert audit["latency_ms"]["count"] == 1


def test_cancel_without_active_chat_returns_conflict(client):
    response = client.post("/chat/cancel", json={})

    assert response.status_code == 409


def test_confirm_unknown_id_returns_not_found(client):
    response = client.post(
        "/chat/confirm",
        json={"request_id": "missing", "approved": True},
    )

    assert response.status_code == 404
