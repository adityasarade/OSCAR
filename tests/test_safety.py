from oscar.core.safety import _assess_risk


def test_git_status_is_low_risk():
    assert _assess_risk("git_status", "git_status") == "low"


def test_git_push_is_medium_risk_by_tool_name():
    assert _assess_risk("git_push", "git_push") == "medium"


def test_shell_rm_root_is_dangerous():
    assert _assess_risk("run_shell_command", "run_shell_command rm -rf /") == "dangerous"


def test_shell_shutdown_is_high_risk():
    assert _assess_risk("run_shell_command", "run_shell_command shutdown now") == "high"


def test_shell_kill_is_medium_risk():
    assert _assess_risk("run_shell_command", "run_shell_command kill 123") == "medium"


def test_medium_tool_escalates_to_high_for_high_risk_args():
    assert _assess_risk("git_push", "git_push shutdown") == "high"
