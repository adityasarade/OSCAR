import subprocess

from oscar.tools import git_tool


def _completed(args, stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_git_branches_parses_local_and_remote_refs(monkeypatch):
    def fake_run(command, capture_output, text):
        if command == ["git", "symbolic-ref", "--quiet", "--short", "HEAD"]:
            return _completed(command, stdout="main\n")
        assert command[:2] == ["git", "for-each-ref"]
        return _completed(
            command,
            stdout="\n".join(
                [
                    "main",
                    "feature/api",
                    "origin/HEAD",
                    "origin/main",
                    "origin/feature/api",
                ]
            ),
        )

    monkeypatch.setattr(git_tool.subprocess, "run", fake_run)

    assert git_tool.git_branches().splitlines() == [
        "* main",
        "  feature/api",
        "  remotes/origin/main",
        "  remotes/origin/feature/api",
    ]


def test_git_status_returns_formatted_non_error_text(monkeypatch):
    def fake_run(command, capture_output, text):
        assert command == ["git", "status", "--porcelain=v2", "--branch"]
        return _completed(
            command,
            stdout="\n".join(
                [
                    "# branch.oid abc123",
                    "# branch.head main",
                    "# branch.upstream origin/main",
                    "# branch.ab +1 -2",
                    "1 .M N... 100644 100644 100644 abc abc src/app.py",
                    "? tests/test_app.py",
                ]
            ),
        )

    monkeypatch.setattr(git_tool.subprocess, "run", fake_run)

    output = git_tool.git_status()

    assert not output.startswith("Error")
    assert "Branch: main" in output
    assert "Upstream: origin/main" in output
    assert "Ahead: 1 Behind: 2" in output
    assert ".M src/app.py" in output
    assert "?? tests/test_app.py" in output
