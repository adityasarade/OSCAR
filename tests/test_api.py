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
    body = response.json()
    # Static fields
    assert body["agent_id"] == "oscar-test"
    assert body["tools"] == ["git_status"]
    assert body["memory_blocks"] == ["session_context"]
    assert body["conversation_length"] == 1
    # New provider/model fields are env-driven and must be present.
    assert "provider" in body
    assert "model" in body


def test_providers_lists_catalog_and_current_selection(client):
    response = client.get("/providers")

    assert response.status_code == 200
    body = response.json()
    provider_ids = [p["id"] for p in body["providers"]]
    # All five providers should be advertised.
    for expected in ("gemini", "openai", "anthropic", "groq", "ollama"):
        assert expected in provider_ids, f"missing provider {expected}"
    assert body["current"]["provider"]
    assert body["current"]["model"]


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
    # Locals come first; remote-tracking duplicates of locals are dropped.
    assert response.json() == {
        "branches": ["main", "feature/api"],
        "current": "main",
        "repo_path": "",
    }


def test_branches_includes_remote_only_branches_with_full_ref(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "git_branches",
        lambda: "\n".join(
            [
                "* main",
                "  remotes/origin/main",
                "  remotes/origin/release-2026",
            ]
        ),
    )

    response = client.get("/branches")

    assert response.status_code == 200
    body = response.json()
    # Local `main` keeps its short form; remote-only branch keeps its
    # full ref so /compare and /review can resolve it.
    assert body["branches"] == ["main", "remotes/origin/release-2026"]
    assert body["current"] == "main"


def test_branches_accepts_repo_path_query(client, monkeypatch, tmp_path):
    captured = {}

    def fake_branches():
        from oscar.core import repo_context

        captured["active_repo"] = repo_context.get_active_repo()
        return "* main"

    monkeypatch.setattr(server, "git_branches", fake_branches)

    response = client.get(
        "/branches",
        params={"repo_path": str(tmp_path)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["repo_path"] == str(tmp_path)
    assert captured["active_repo"] == str(tmp_path.resolve())


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
