import importlib


def test_workspace_clone_keeps_original_clean(sample_repo):
    assert importlib.util.find_spec("core.local_workspace"), "Missing isolated workspace"
    from core.local_workspace import isolated_workspace

    (sample_repo / "calc.py").write_text("uncommitted original\n")
    with isolated_workspace(sample_repo) as workspace:
        (workspace / "calc.py").write_text("agent change\n")
        assert (sample_repo / "calc.py").read_text() == "uncommitted original\n"
    assert not workspace.exists()


def test_verification_binds_repo_issue_patch(tmp_path):
    assert importlib.util.find_spec("core.verification"), "Missing verification gate"
    from core.verification import is_verified, save_verification

    state = {
        "terminal_status": "resolved",
        "test_report": {
            "project_type": "Python",
            "results": [{"command": "python_pytest", "exit_code": 0, "status": "passed"}],
            "all_required_passed": True,
        },
        "review_decision": {"verdict": "pass", "reasons": []},
    }
    save_verification("o/r", 1, "patch", state, tmp_path)
    assert is_verified("o/r", 1, "patch", tmp_path)
    assert not is_verified("o/r", 2, "patch", tmp_path)
    assert not is_verified("o/r", 1, "altered", tmp_path)
    save_verification("o/r", 1, "patch", {}, tmp_path)
    assert not is_verified("o/r", 1, "patch", tmp_path)


def test_receipt_requires_same_base(tmp_path):
    from core.verification import is_verified, save_verification

    state = {
        "terminal_status": "resolved",
        "test_report": {
            "project_type": "Python",
            "results": [{"command": "python_pytest", "exit_code": 0, "status": "passed"}],
            "all_required_passed": True,
        },
        "review_decision": {"verdict": "pass", "reasons": []},
    }
    save_verification("o/r", 1, "patch", state, tmp_path, base_commit="abc")
    assert is_verified("o/r", 1, "patch", tmp_path, base_commit="abc")
    assert not is_verified("o/r", 1, "patch", tmp_path, base_commit="def")
