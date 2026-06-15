from pathlib import Path

import pytest

from eval.unified_models import UnifiedCase
from eval.unified_preparers import LocalFixturePreparer


def test_local_fixture_preparer_creates_git_baseline(tmp_path):
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
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
    )

    prepared = LocalFixturePreparer(tmp_path).prepare(case)

    assert prepared.workspace == tmp_path / "workspaces" / "py-single-file"
    assert len(prepared.base_commit) == 40
    assert (prepared.workspace / ".git").exists()
    assert (prepared.workspace / "autopatch_demo" / "calculator.py").exists()


def test_local_fixture_preparer_requires_fixture_path(tmp_path):
    case = UnifiedCase(
        case_id="missing-fixture",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/missing",
        base_commit=None,
        issue_title="Missing fixture",
        issue_body="No fixture path.",
        language="Python",
        fail_to_pass=[],
        pass_to_pass=[],
    )

    with pytest.raises(ValueError, match="missing-fixture has no fixture_path"):
        LocalFixturePreparer(tmp_path).prepare(case)
