"""
eval/config.py
--------------
评测配置。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class EvalConfig:
    # ── 数据集 ──
    dataset_name: str = "princeton-nlp/SWE-bench_Lite"
    dataset_split: str = "test"
    instance_ids: Optional[List[str]] = None
    repos: Optional[List[str]] = None
    max_instances: Optional[int] = None
    shuffle: bool = False
    seed: int = 42

    # ── 执行 ──
    concurrency: int = 1
    timeout_per_instance: int = 600
    recursion_limit: int = 100
    model_name: Optional[str] = None

    # ── 环境 ──
    workdir_base: str = "/tmp/autopatch_eval"
    install_deps: bool = True
    python_bin: str = "python"

    # ── 续跑 ──
    results_dir: str = "eval/results"
    run_id: Optional[str] = None
    resume: bool = True

    # ── Docker ──
    use_docker: bool = False
    docker_image_prefix: str = "swebench/sweb.eval.x86_64"
    keep_image: bool = False

    def resolve_run_id(self) -> str:
        if self.run_id is None:
            self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.run_id

    # ── CLI 解析 ──
    @classmethod
    def from_cli(cls, argv: Optional[List[str]] = None) -> "EvalConfig":
        p = argparse.ArgumentParser(description="AutoPatch SWE-bench 评测")

        p.add_argument("--dataset", default=cls.dataset_name, dest="dataset_name")
        p.add_argument("--split", default=cls.dataset_split, dest="dataset_split")
        p.add_argument("--instance-ids", nargs="+", default=None)
        p.add_argument("--repos", nargs="+", default=None)
        p.add_argument("--max-instances", type=int, default=None)
        p.add_argument("--shuffle", action="store_true")
        p.add_argument("--seed", type=int, default=42)

        p.add_argument("--concurrency", type=int, default=1)
        p.add_argument("--timeout", type=int, default=600, dest="timeout_per_instance")
        p.add_argument("--recursion-limit", type=int, default=100)
        p.add_argument("--model", default=None, dest="model_name")

        p.add_argument("--workdir", default="/tmp/autopatch_eval", dest="workdir_base")
        p.add_argument("--no-install", action="store_true")
        p.add_argument("--python", default="python", dest="python_bin")

        p.add_argument("--results-dir", default="eval/results")
        p.add_argument("--run-id", default=None)
        p.add_argument("--no-resume", action="store_true")

        p.add_argument("--docker", action="store_true", default=False)
        p.add_argument("--keep-image", action="store_true", default=False)
        p.add_argument(
            "--docker-image-prefix",
            default="swebench/sweb.eval.x86_64",
            dest="docker_image_prefix",
        )

        args = p.parse_args(argv)

        return cls(
            dataset_name=args.dataset_name,
            dataset_split=args.dataset_split,
            instance_ids=args.instance_ids,
            repos=args.repos,
            max_instances=args.max_instances,
            shuffle=args.shuffle,
            seed=args.seed,
            concurrency=args.concurrency,
            timeout_per_instance=args.timeout_per_instance,
            recursion_limit=args.recursion_limit,
            model_name=args.model_name,
            workdir_base=args.workdir_base,
            install_deps=not args.no_install,
            python_bin=args.python_bin,
            results_dir=args.results_dir,
            run_id=args.run_id,
            resume=not args.no_resume,
            use_docker=args.docker,
            docker_image_prefix=args.docker_image_prefix,
            keep_image=args.keep_image,
        )
