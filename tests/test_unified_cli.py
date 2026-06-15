import json
from pathlib import Path

from eval.unified import build_parser, resolve_cases


def test_parser_accepts_sanity_agent_mode():
    args = build_parser().parse_args(["--dataset", "sanity-v2", "--mode", "agent"])

    assert args.dataset == "sanity-v2"
    assert args.mode == "agent"


def test_resolve_cases_loads_selected_sanity_case():
    args = build_parser().parse_args(
        [
            "--dataset",
            "sanity-v1",
            "--mode",
            "baseline-only",
            "--case-ids",
            "py-single-file",
        ]
    )

    cases = resolve_cases(args)

    assert [case.case_id for case in cases] == ["py-single-file"]


def test_resolve_cases_loads_local_json_swebench_instance():
    dataset_path = Path("tmp_local_dataset.json")
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "instance_id": "local__case-1",
                    "repo": "dummy/repo",
                    "base_commit": "abc",
                    "problem_statement": "Update edge-case handling.",
                    "test_patch": "diff --git a/tests/test.py b/tests/test.py\n",
                    "patch": "gold",
                    "FAIL_TO_PASS": ["tests/test.py::test_bug"],
                    "PASS_TO_PASS": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    try:
        args = build_parser().parse_args(
            [
                "--dataset",
                str(dataset_path),
                "--mode",
                "baseline-only",
                "--instance-ids",
                "local__case-1",
            ]
        )
        cases = resolve_cases(args)
    finally:
        dataset_path.unlink(missing_ok=True)

    assert [case.case_id for case in cases] == ["local__case-1"]
