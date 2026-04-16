"""
eval/runner.py
--------------
批量评测运行器，支持顺序/并行执行与断点续跑。
"""

from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Set

import logging

from eval.config import EvalConfig
from eval.dataset import SWEBenchInstance, load_dataset
from eval.evaluator import InstanceEvaluator, InstanceResult
from eval.metrics import (
    AggregateMetrics,
    compute_aggregate,
    print_summary,
    save_aggregate_report,
    save_instance_result,
)

logger = logging.getLogger(__name__)


class EvalRunner:
    """编排批量评测。"""

    def __init__(self, config: EvalConfig):
        self.config = config
        self.run_id = config.resolve_run_id()
        self.results_dir = Path(config.results_dir)

    def run(self) -> AggregateMetrics:
        # 1. 加载数据集
        logger.info(f"[EvalRunner] 加载数据集: {self.config.dataset_name}")
        instances = load_dataset(self.config)
        logger.info(f"[EvalRunner] 加载 {len(instances)} 个实例")

        if not instances:
            logger.info("[EvalRunner] 无可评测实例")
            return AggregateMetrics()

        # 2. 断点续跑：跳过已完成
        completed_ids = self._get_completed_ids() if self.config.resume else set()
        remaining = [i for i in instances if i.instance_id not in completed_ids]

        if completed_ids:
            logger.info(f"[EvalRunner] 续跑模式：跳过 {len(completed_ids)} 个已完成实例")
        logger.info(f"[EvalRunner] 待评测: {len(remaining)} 个实例")

        # 3. 执行评测
        if self.config.concurrency <= 1:
            new_results = self._run_sequential(remaining)
        else:
            new_results = self._run_parallel(remaining)

        # 4. 合并已完成的结果
        all_results = self._load_completed_results(completed_ids) + new_results

        # 5. 计算聚合指标
        metrics = compute_aggregate(all_results)

        # 6. 保存报告
        config_dict = dataclasses.asdict(self.config)
        save_aggregate_report(metrics, all_results, self.results_dir, self.run_id, config_dict)

        # 7. 打印汇总
        print_summary(metrics)

        report_path = self.results_dir / self.run_id / "report.md"
        logger.info(f"\n[EvalRunner] 报告已保存: {report_path}")

        return metrics

    def _get_completed_ids(self) -> Set[str]:
        """扫描已完成的实例 ID。"""
        inst_dir = self.results_dir / self.run_id / "instances"
        if not inst_dir.exists():
            return set()
        return {p.stem for p in inst_dir.glob("*.json")}

    def _load_completed_results(self, completed_ids: Set[str]) -> List[InstanceResult]:
        """从磁盘加载已完成的 InstanceResult。"""
        results = []
        inst_dir = self.results_dir / self.run_id / "instances"
        for iid in completed_ids:
            fpath = inst_dir / f"{iid}.json"
            if fpath.exists():
                data = json.loads(fpath.read_text(encoding="utf-8"))
                results.append(InstanceResult(
                    instance_id=data["instance_id"],
                    repo=data.get("repo", ""),
                    resolved=data.get("resolved", False),
                    status=data.get("status", "error"),
                    agent_patch=data.get("agent_patch", ""),
                    review_result=data.get("review_result", ""),
                    step_count=data.get("step_count", 0),
                    elapsed_seconds=data.get("elapsed_seconds", 0.0),
                    fail_to_pass_results=data.get("fail_to_pass_results", {}),
                    pass_to_pass_results=data.get("pass_to_pass_results", {}),
                    error_message=data.get("error_message"),
                    baseline_valid=data.get("baseline_valid", True),
                ))
        return results

    def _evaluate_single(self, idx: int, total: int, instance: SWEBenchInstance) -> InstanceResult:
        """评测单个实例，附带进度输出和持久化。"""
        logger.info(f"\n[{idx}/{total}] {instance.instance_id} ...")
        evaluator = InstanceEvaluator(instance, self.config)
        result = evaluator.evaluate()

        status_icon = {
            "resolved": "OK",
            "partially_resolved": "PARTIAL",
            "failed": "FAIL",
            "error": "ERR",
            "timeout": "TIMEOUT",
        }.get(result.status, "?")
        logger.info(f"[{idx}/{total}] {instance.instance_id} -> {status_icon} ({result.elapsed_seconds:.0f}s)")

        # 立即持久化
        save_instance_result(result, self.results_dir, self.run_id)
        return result

    def _run_sequential(self, instances: List[SWEBenchInstance]) -> List[InstanceResult]:
        total = len(instances)
        results = []
        for idx, inst in enumerate(instances, 1):
            result = self._evaluate_single(idx, total, inst)
            results.append(result)
        return results

    def _run_parallel(self, instances: List[SWEBenchInstance]) -> List[InstanceResult]:
        total = len(instances)
        results = []
        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = {
                executor.submit(self._evaluate_single, idx, total, inst): inst
                for idx, inst in enumerate(instances, 1)
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    inst = futures[future]
                    logger.error(f"[EvalRunner] {inst.instance_id} 异常: {e}")
                    results.append(InstanceResult(
                        instance_id=inst.instance_id,
                        repo=inst.repo,
                        status="error",
                        error_message=str(e),
                    ))
        return results
