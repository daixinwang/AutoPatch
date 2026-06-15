import json
from pathlib import Path

from eval.unified_providers import (
    DEFAULT_SWEBENCH_SMOKE_IDS,
    LocalSanityProvider,
    SWEBenchProvider,
    SWEBenchSmokeProvider,
)


def test_local_sanity_provider_loads_existing_case():
    provider = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    )

    cases = provider.load()
    case = next(item for item in cases if item.case_id == "py-single-file")

    assert len(cases) == 5
    assert case.dataset_name == "sanity-v1"
    assert case.workspace_strategy == "local_fixture"
    assert case.fixture_path == Path("eval/fixtures/sanity-v1/py-single-file")
    assert case.fail_to_pass == [
        "tests/test_calculator.py::test_percentage_discount_uses_percent_units"
    ]
    assert case.allow_test_modifications is False


def test_swebench_provider_loads_local_json_and_filters(tmp_path):
    data = [
        {
            "instance_id": "django__django-100",
            "repo": "django/django",
            "base_commit": "abc123",
            "problem_statement": "Fix query behavior.",
            "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n",
            "patch": "gold diff",
            "FAIL_TO_PASS": json.dumps(["tests.test_x.TestCase.test_bug"]),
            "PASS_TO_PASS": ["tests.test_x.TestCase.test_existing"],
            "version": "4.2",
            "environment_setup_commit": "env123",
        },
        {
            "instance_id": "sympy__sympy-200",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "problem_statement": "Fix simplify behavior.",
            "test_patch": "",
            "patch": "",
            "FAIL_TO_PASS": ["sympy/test_bug.py::test_bug"],
            "PASS_TO_PASS": [],
        },
    ]
    dataset = tmp_path / "swebench.json"
    dataset.write_text(json.dumps(data), encoding="utf-8")

    provider = SWEBenchProvider(
        dataset_name=str(dataset),
        dataset_split="test",
        instance_ids=["django__django-100"],
    )

    cases = provider.load()

    assert [case.case_id for case in cases] == ["django__django-100"]
    assert cases[0].dataset_name == "swebench-lite"
    assert cases[0].workspace_strategy == "swebench_instance"
    assert cases[0].issue_title == "SWE-bench issue django__django-100"
    assert cases[0].issue_body == "Fix query behavior."
    assert cases[0].swebench_gold_patch == "gold diff"
    assert cases[0].fail_to_pass == ["tests.test_x.TestCase.test_bug"]


def test_swebench_smoke_provider_uses_pinned_ids(tmp_path):
    data = []
    for instance_id in DEFAULT_SWEBENCH_SMOKE_IDS:
        data.append(
            {
                "instance_id": instance_id,
                "repo": "django/django",
                "base_commit": "abc123",
                "problem_statement": f"Problem for {instance_id}",
                "test_patch": "",
                "patch": "",
                "FAIL_TO_PASS": ["tests.test_x.TestCase.test_bug"],
                "PASS_TO_PASS": [],
            }
        )
    data.append(
        {
            "instance_id": "extra__case-1",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "problem_statement": "Extra problem.",
            "test_patch": "",
            "patch": "",
            "FAIL_TO_PASS": ["test_extra.py::test_bug"],
            "PASS_TO_PASS": [],
        }
    )
    dataset = tmp_path / "swebench.json"
    dataset.write_text(json.dumps(data), encoding="utf-8")

    provider = SWEBenchSmokeProvider(dataset_name=str(dataset), dataset_split="test")
    cases = provider.load()

    assert [case.case_id for case in cases] == DEFAULT_SWEBENCH_SMOKE_IDS
