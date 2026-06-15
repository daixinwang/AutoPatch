#!/usr/bin/env python3
"""
eval/unified.py
----------------
统一评测 CLI（sanity + SWE-bench）入口。
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from eval.config import EvalConfig
from eval.unified_providers import (
    LocalSanityProvider,
    SWEBenchProvider,
    SWEBenchSmokeProvider,
)
from eval.unified_runner import EvalMode, UnifiedEvalRunner
from eval.unified_models import UnifiedCase


DEFAULT_SWEBENCH_SMOKE_DATASET = "princeton-nlp/SWE-bench_Lite"
DEFAULT_SWEBENCH_LITE_DATASET = "princeton-nlp/SWE-bench_Lite"
DEFAULT_DATASET_SPLIT = "test"
DEFAULT_DATASET_CASES_DIR = Path("eval/cases")


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="AutoPatch unified evaluation runner")
    parser.add_argument(
        "--dataset",
        required=True,
        help=(
            "Dataset selector. Built-in: sanity-v1, sanity-v2, swebench-smoke, "
            "swebench-lite; or local SWE-bench JSON path / HF dataset id."
        ),
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("baseline-only", "mock-patch", "agent"),
        help="Evaluation mode",
    )

    parser.add_argument("--results-dir", default="eval/results")
    parser.add_argument("--run-id")
    parser.add_argument("--cases-dir", default=str(DEFAULT_DATASET_CASES_DIR))
    parser.add_argument("--mock-patch-dir")
    parser.add_argument("--dataset-split", default=DEFAULT_DATASET_SPLIT)
    parser.add_argument("--instance-ids", nargs="+")
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--repos", nargs="+")
    parser.add_argument("--max-instances", type=int)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--workdir", default="/tmp/autopatch_eval")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--keep-image", action="store_true")
    return parser


def _filter_cases_by_ids(cases: List[UnifiedCase], case_ids: List[str]) -> List[UnifiedCase]:
    by_id = {case.case_id: case for case in cases}
    return [by_id[case_id] for case_id in case_ids if case_id in by_id]


def resolve_cases(args: Namespace) -> List[UnifiedCase]:
    if args.dataset in {"sanity-v1", "sanity-v2"}:
        cases_dir = Path(args.cases_dir) / args.dataset
        provider = LocalSanityProvider(dataset_name=args.dataset, cases_dir=cases_dir)
        cases = provider.load()
        if args.case_ids:
            return _filter_cases_by_ids(cases, args.case_ids)
        if args.instance_ids:
            return _filter_cases_by_ids(cases, args.instance_ids)
        return cases

    if args.dataset == "swebench-smoke":
        cases = SWEBenchSmokeProvider(
            dataset_name=DEFAULT_SWEBENCH_SMOKE_DATASET,
            dataset_split=args.dataset_split,
            repos=args.repos,
            shuffle=args.shuffle,
            seed=args.seed,
            max_instances=args.max_instances,
        ).load()
        if args.instance_ids:
            return _filter_cases_by_ids(cases, args.instance_ids)
        return cases

    if args.dataset == "swebench-lite":
        return SWEBenchProvider(
            dataset_name=DEFAULT_SWEBENCH_LITE_DATASET,
            dataset_split=args.dataset_split,
            instance_ids=args.instance_ids,
            repos=args.repos,
            shuffle=args.shuffle,
            seed=args.seed,
            max_instances=args.max_instances,
        ).load()

    return SWEBenchProvider(
        dataset_name=args.dataset,
        dataset_split=args.dataset_split,
        instance_ids=args.instance_ids,
        repos=args.repos,
        shuffle=args.shuffle,
        seed=args.seed,
        max_instances=args.max_instances,
    ).load()


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "mock-patch" and not args.mock_patch_dir:
        raise RuntimeError("--mock-patch-dir is required when mode is mock-patch")

    cases = resolve_cases(args)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    config = EvalConfig(
        dataset_name=args.dataset,
        dataset_split=args.dataset_split,
        instance_ids=args.instance_ids,
        repos=args.repos,
        max_instances=args.max_instances,
        shuffle=args.shuffle,
        seed=args.seed,
        workdir_base=args.workdir,
        install_deps=not args.no_install,
        results_dir=args.results_dir,
        run_id=run_id,
        use_docker=args.docker,
        keep_image=args.keep_image,
    )

    runner = UnifiedEvalRunner(
        cases=cases,
        run_id=run_id,
        results_dir=Path(args.results_dir),
        mode=args.mode,
        mock_patch_dir=Path(args.mock_patch_dir) if args.mock_patch_dir else None,
        eval_config=config,
    )
    runner.run()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
