import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from eval.unified import DEFAULT_SWEBENCH_SMOKE_DATASET, build_parser, resolve_cases


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


def test_resolve_cases_swebench_smoke_uses_lite_dataset(monkeypatch):
    captured = {}

    class FakeSmokeProvider:
        def __init__(
            self,
            dataset_name,
            dataset_split,
            repos,
            shuffle,
            seed,
            max_instances,
        ):
            captured["dataset_name"] = dataset_name
            captured["dataset_split"] = dataset_split
            captured["repos"] = repos
            captured["shuffle"] = shuffle
            captured["seed"] = seed
            captured["max_instances"] = max_instances

        def load(self):
            return []

    monkeypatch.setattr("eval.unified.SWEBenchSmokeProvider", FakeSmokeProvider)

    args = build_parser().parse_args(
        [
            "--dataset",
            "swebench-smoke",
            "--mode",
            "agent",
            "--dataset-split",
            "train",
            "--seed",
            "7",
        ]
    )

    cases = resolve_cases(args)

    assert captured["dataset_name"] == DEFAULT_SWEBENCH_SMOKE_DATASET
    assert captured["dataset_split"] == "train"
    assert captured["repos"] is None
    assert captured["shuffle"] is False
    assert captured["seed"] == 7
    assert captured["max_instances"] is None
    assert cases == []


def test_unified_cli_loads_dotenv_before_core_config(tmp_path):
    (tmp_path / ".env").write_text(
        "PLANNER_MODEL_NAME=dotenv-planner-test\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env.pop("PLANNER_MODEL_NAME", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import eval.unified; import core.config as c; print(c.PLANNER_MODEL_NAME)",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "dotenv-planner-test"
