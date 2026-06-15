import json
from pathlib import Path

from eval.sanity import (
    _write_report_md,
    run_baseline_only,
    run_dataset_with_agent,
    run_dataset_baseline_only,
    run_dataset_with_mock_patches,
    run_with_agent,
    run_with_mock_patch,
)


def test_baseline_only_writes_results_for_valid_case(tmp_path):
    result = run_baseline_only(
        case_file=Path("eval/cases/sanity-v1/py-single-file.json"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    case_dir = tmp_path / "test-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    workspace_info = json.loads((case_dir / "workspace-info.json").read_text(encoding="utf-8"))

    assert result.verdict == "baseline_ready"
    assert verdict["verdict"] == "baseline_ready"
    assert verdict["fail_to_pass"]["failed"] == [
        "tests/test_calculator.py::test_percentage_discount_uses_percent_units"
    ]
    assert verdict["pass_to_pass"]["passed"] == 1
    assert (case_dir / "case.json").exists()
    assert (case_dir / "issue.md").read_text(encoding="utf-8").startswith("# Percentage discounts")
    assert (case_dir / "test-before.log").exists()
    assert len(workspace_info["base_commit"]) == 40


def test_baseline_only_marks_invalid_case_when_f2p_already_passes(tmp_path):
    result = run_baseline_only(
        case_file=Path("eval/cases/sanity-v1/invalid-baseline.json"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    case_dir = tmp_path / "test-run" / "cases" / "invalid-baseline"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert result.verdict == "invalid_case"
    assert verdict["verdict"] == "invalid_case"
    assert "already pass" in verdict["reason"]
    assert verdict["fail_to_pass"]["passed"] == 1


def test_dataset_baseline_only_writes_aggregate_reports(tmp_path):
    results = run_dataset_baseline_only(
        cases_dir=Path("eval/cases/sanity-v1"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    run_dir = tmp_path / "test-run"
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))

    assert len(results) == 5
    assert report["total_cases"] == 5
    assert report["baseline_ready"] == 4
    assert report["invalid_case"] == 1
    assert report["infra_error"] == 0
    assert config["dataset_name"] == "sanity-v1"
    assert (run_dir / "report.md").exists()


def test_report_md_uses_dataset_name_in_title(tmp_path):
    report_path = tmp_path / "report.md"

    _write_report_md(
        report_path,
        {
            "run_id": "test-run",
            "dataset_name": "sanity-v2",
            "total_cases": 0,
            "cases": [],
        },
    )

    assert report_path.read_text(encoding="utf-8").startswith("# sanity-v2 Report")


def test_mock_patch_marks_resolved_for_correct_patch(tmp_path):
    result = run_with_mock_patch(
        case_file=Path("eval/cases/sanity-v1/py-single-file.json"),
        patch_file=Path("eval/mock_patches/sanity-v1/resolved/py-single-file.diff"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    case_dir = tmp_path / "test-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    changed_files = json.loads((case_dir / "changed-files.json").read_text(encoding="utf-8"))

    assert result.verdict == "resolved"
    assert verdict["verdict"] == "resolved"
    assert verdict["patch_applies"] is True
    assert verdict["fail_to_pass"]["passed"] == 1
    assert verdict["pass_to_pass"]["passed"] == 1
    assert changed_files == [
        {
            "path": "autopatch_demo/calculator.py",
            "is_test": False,
            "change_type": "modified",
        }
    ]
    assert "discount_percent / 100" in (case_dir / "patch.diff").read_text(encoding="utf-8")
    assert (case_dir / "test-after.log").exists()


def test_mock_patch_rejects_test_file_modification(tmp_path):
    result = run_with_mock_patch(
        case_file=Path("eval/cases/sanity-v1/py-test-modification-guard.json"),
        patch_file=Path("eval/mock_patches/sanity-v1/test-modification/py-test-modification-guard.diff"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    case_dir = tmp_path / "test-run" / "cases" / "py-test-modification-guard"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    changed_files = json.loads((case_dir / "changed-files.json").read_text(encoding="utf-8"))

    assert result.verdict == "failed"
    assert verdict["verdict"] == "failed"
    assert verdict["failure_category"] == "test_modification"
    assert verdict["modified_test_files"] is True
    assert changed_files[0]["path"] == "tests/test_username.py"
    assert changed_files[0]["is_test"] is True


def test_mock_patch_marks_partial_for_regression(tmp_path):
    result = run_with_mock_patch(
        case_file=Path("eval/cases/sanity-v1/py-regression-risk.json"),
        patch_file=Path("eval/mock_patches/sanity-v1/regression/py-regression-risk.diff"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    case_dir = tmp_path / "test-run" / "cases" / "py-regression-risk"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert result.verdict == "partial"
    assert verdict["verdict"] == "partial"
    assert verdict["failure_category"] == "regression"
    assert verdict["fail_to_pass"]["passed"] == 1
    assert verdict["pass_to_pass"]["failed"] == [
        "tests/test_slugify.py::test_slugify_preserves_punctuation_separated_words"
    ]


def test_mock_patch_reports_patch_apply_failure(tmp_path):
    result = run_with_mock_patch(
        case_file=Path("eval/cases/sanity-v1/py-single-file.json"),
        patch_file=Path("eval/mock_patches/sanity-v1/patch-apply-failure/py-single-file.diff"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    case_dir = tmp_path / "test-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert result.verdict == "failed"
    assert verdict["verdict"] == "failed"
    assert verdict["patch_applies"] is False
    assert verdict["failure_category"] == "patch_apply_failure"


def test_dataset_mock_patch_dir_writes_final_aggregate_reports(tmp_path):
    results = run_dataset_with_mock_patches(
        cases_dir=Path("eval/cases/sanity-v1"),
        patch_dir=Path("eval/mock_patches/sanity-v1/resolved"),
        results_dir=tmp_path,
        run_id="test-run",
    )

    run_dir = tmp_path / "test-run"
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))

    assert len(results) == 5
    assert report["total_cases"] == 5
    assert report["resolved"] == 4
    assert report["invalid_case"] == 1
    assert report["failed"] == 0
    assert report["partial"] == 0
    assert config["agent_config"]["mode"] == "mock_patch"
    assert config["mock_patch_dir"] == "eval/mock_patches/sanity-v1/resolved"


def test_agent_run_uses_workspace_changes_and_writes_trace(tmp_path):
    def fake_agent(issue_text: str, working_dir: str, repo_language: str):
        target = Path(working_dir) / "autopatch_demo" / "calculator.py"
        target.write_text(
            "def calculate_discounted_total(subtotal: float, discount_percent: float) -> float:\n"
            "    \"\"\"Return subtotal after applying a percentage discount.\"\"\"\n"
            "    return subtotal - (subtotal * discount_percent / 100)\n",
            encoding="utf-8",
        )
        return {"review_result": "PASS\nReason: fake agent fixed the bug", "step_count": 3}

    result = run_with_agent(
        case_file=Path("eval/cases/sanity-v1/py-single-file.json"),
        results_dir=tmp_path,
        run_id="test-run",
        agent_runner=fake_agent,
    )

    case_dir = tmp_path / "test-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    trace_lines = (case_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()

    assert result.verdict == "resolved"
    assert verdict["verdict"] == "resolved"
    assert verdict["agent_result"]["step_count"] == 3
    assert "discount_percent / 100" in (case_dir / "patch.diff").read_text(encoding="utf-8")
    assert any('"type": "agent_started"' in line for line in trace_lines)
    assert any('"type": "agent_finished"' in line for line in trace_lines)
    assert any('"verdict": "resolved"' in line for line in trace_lines)


def test_dataset_agent_skips_invalid_baseline_without_calling_agent(tmp_path):
    def agent_must_not_run(issue_text: str, working_dir: str, repo_language: str):
        raise AssertionError("agent should not run for invalid baseline")

    results = run_dataset_with_agent(
        cases_dir=Path("eval/cases/sanity-v1"),
        results_dir=tmp_path,
        run_id="test-run",
        case_ids=["invalid-baseline"],
        agent_runner=agent_must_not_run,
    )

    run_dir = tmp_path / "test-run"
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))

    assert [result.case_id for result in results] == ["invalid-baseline"]
    assert results[0].verdict == "invalid_case"
    assert report["total_cases"] == 1
    assert report["invalid_case"] == 1
    assert report["resolved"] == 0
