from pathlib import Path
from typing import Any, Dict, List, Optional, Set, get_type_hints

from eval.unified_models import (
    ChangedFile,
    UnifiedCase,
    Verdict,
    PreparedWorkspace,
    classify_changed_file,
    is_test_path,
)


def test_is_test_path_detects_common_test_locations():
    assert is_test_path("tests/test_checkout.py")
    assert is_test_path("pkg/__tests__/widget.test.tsx")
    assert is_test_path("src/foo_test.py")
    assert not is_test_path("shop/pricing.py")


def test_classify_changed_file_maps_git_status():
    changed = classify_changed_file("M", "tests/test_checkout.py")

    assert changed == ChangedFile(
        path="tests/test_checkout.py",
        is_test=True,
        change_type="modified",
    )


def test_classify_changed_file_maps_git_statuses_for_add_delete_and_rename():
    assert classify_changed_file("A", "src/new_feature.py") == ChangedFile(
        path="src/new_feature.py",
        is_test=False,
        change_type="added",
    )
    assert classify_changed_file("D", "src/removed.py") == ChangedFile(
        path="src/removed.py",
        is_test=False,
        change_type="deleted",
    )
    assert classify_changed_file("R100", "src/renamed.py") == ChangedFile(
        path="src/renamed.py",
        is_test=False,
        change_type="renamed",
    )


def test_unified_case_issue_markdown_excludes_analysis_fields():
    case = UnifiedCase(
        case_id="py-single-file",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/sanity-py-single-file",
        base_commit=None,
        issue_title="Percentage discounts are 100x too large",
        issue_body="Fix the discount calculation.",
        language="Python",
        fail_to_pass=["tests/test_calculator.py::test_percentage_discount_uses_percent_units"],
        pass_to_pass=["tests/test_calculator.py::test_zero_discount_keeps_subtotal"],
        expected_files=["autopatch_demo/calculator.py"],
        allow_test_modifications=False,
        workspace_strategy="local_fixture",
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
        analysis_notes="Do not pass this to agent.",
        swebench_gold_patch="gold patch should stay hidden",
    )

    markdown = case.issue_markdown()

    assert markdown == "# Percentage discounts are 100x too large\n\nFix the discount calculation.\n"
    assert "gold patch" not in markdown
    assert "Do not pass" not in markdown


def test_verdict_values_match_protocol():
    assert [item.value for item in Verdict] == [
        "resolved",
        "partial",
        "failed",
        "agent_timeout",
        "infra_error",
        "invalid_case",
        "baseline_ready",
    ]


def test_unified_case_to_case_json_preserves_auxiliary_fields():
    case = UnifiedCase(
        case_id="py-single-file",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/sanity-py-single-file",
        base_commit=None,
        issue_title="Percentage discounts are 100x too large",
        issue_body="Fix the discount calculation.",
        language="Python",
        fail_to_pass=["tests/test_calculator.py::test_percentage_discount_uses_percent_units"],
        pass_to_pass=["tests/test_calculator.py::test_zero_discount_keeps_subtotal"],
        expected_files=["autopatch_demo/calculator.py"],
        allow_test_modifications=False,
        workspace_strategy="local_fixture",
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
        swebench_test_patch="--- a/x.py\n+++ b/x.py\n@@ -1 +1\n+pass",
        swebench_gold_patch="gold patch",
        analysis_notes="Do not pass this to agent.",
        raw={"note": "important"},
    )

    payload = case.to_case_json()

    assert payload["swebench_test_patch"] == "--- a/x.py\n+++ b/x.py\n@@ -1 +1\n+pass"
    assert payload["swebench_gold_patch"] == "gold patch"
    assert payload["analysis_notes"] == "Do not pass this to agent."
    assert payload["raw"] == {"note": "important"}


def test_unified_case_and_workspace_type_hints_are_compatible_with_python_39():
    case_hints = get_type_hints(UnifiedCase)

    assert case_hints["base_commit"] == Optional[str]
    assert case_hints["fail_to_pass"] == List[str]
    assert case_hints["pass_to_pass"] == List[str]
    assert case_hints["expected_files"] == List[str]
    assert case_hints["fixture_path"] == Optional[Path]
    assert case_hints["swebench_instance_id"] == Optional[str]
    assert case_hints["environment_setup_commit"] == Optional[str]
    assert case_hints["version"] == Optional[str]
    assert case_hints["analysis_notes"] == Optional[str]
    assert case_hints["raw"] == Dict[str, Any]

    workspace = get_type_hints(PreparedWorkspace)
    assert workspace["test_patch_files"] == Set[str]
    assert workspace["cleanup"] == Optional[Any]
