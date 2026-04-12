"""
eval/metrics.py
---------------
指标计算、结果持久化与报告生成。
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from eval.evaluator import InstanceResult


@dataclass
class RepoMetrics:
    repo: str
    total: int = 0
    resolved: int = 0

    @property
    def resolve_rate(self) -> float:
        return self.resolved / self.total if self.total > 0 else 0.0


@dataclass
class AggregateMetrics:
    total_instances: int = 0
    resolved: int = 0
    partially_resolved: int = 0
    failed: int = 0
    errors: int = 0
    timeouts: int = 0
    resolve_rate: float = 0.0
    avg_elapsed_seconds: float = 0.0
    median_elapsed_seconds: float = 0.0
    avg_step_count: float = 0.0
    by_repo: Dict[str, RepoMetrics] = field(default_factory=dict)


def compute_aggregate(results: List[InstanceResult]) -> AggregateMetrics:
    """从实例结果列表计算聚合指标。"""
    m = AggregateMetrics()
    m.total_instances = len(results)

    if not results:
        return m

    times = []
    steps = []

    for r in results:
        if r.status == "resolved":
            m.resolved += 1
        elif r.status == "partially_resolved":
            m.partially_resolved += 1
        elif r.status == "failed":
            m.failed += 1
        elif r.status == "timeout":
            m.timeouts += 1
        else:
            m.errors += 1

        times.append(r.elapsed_seconds)
        steps.append(r.step_count)

        # 按 repo 统计
        if r.repo not in m.by_repo:
            m.by_repo[r.repo] = RepoMetrics(repo=r.repo)
        m.by_repo[r.repo].total += 1
        if r.resolved:
            m.by_repo[r.repo].resolved += 1

    m.resolve_rate = m.resolved / m.total_instances
    m.avg_elapsed_seconds = statistics.mean(times)
    m.median_elapsed_seconds = statistics.median(times)
    m.avg_step_count = statistics.mean(steps)

    return m


# ── 持久化 ──

def save_instance_result(result: InstanceResult, results_dir: Path, run_id: str) -> None:
    """保存单个实例结果为 JSON + patch 文件。"""
    run_dir = results_dir / run_id

    # instance JSON
    inst_dir = run_dir / "instances"
    inst_dir.mkdir(parents=True, exist_ok=True)
    inst_file = inst_dir / f"{result.instance_id}.json"
    inst_file.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # patch file
    if result.agent_patch:
        patch_dir = run_dir / "patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        patch_file = patch_dir / f"{result.instance_id}.diff"
        patch_file.write_text(result.agent_patch, encoding="utf-8")


def save_aggregate_report(
    metrics: AggregateMetrics,
    results: List[InstanceResult],
    results_dir: Path,
    run_id: str,
    config_dict: dict | None = None,
) -> None:
    """保存聚合报告（JSON + Markdown）。"""
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # config.json
    if config_dict:
        (run_dir / "config.json").write_text(
            json.dumps(config_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # report.json
    report_data = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "total_instances": metrics.total_instances,
        "resolved": metrics.resolved,
        "partially_resolved": metrics.partially_resolved,
        "failed": metrics.failed,
        "errors": metrics.errors,
        "timeouts": metrics.timeouts,
        "resolve_rate": round(metrics.resolve_rate, 4),
        "avg_elapsed_seconds": round(metrics.avg_elapsed_seconds, 2),
        "median_elapsed_seconds": round(metrics.median_elapsed_seconds, 2),
        "avg_step_count": round(metrics.avg_step_count, 2),
        "by_repo": {
            repo: {
                "total": rm.total,
                "resolved": rm.resolved,
                "resolve_rate": round(rm.resolve_rate, 4),
            }
            for repo, rm in metrics.by_repo.items()
        },
    }
    (run_dir / "report.json").write_text(
        json.dumps(report_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # report.md
    md = _build_markdown_report(metrics, run_id)
    (run_dir / "report.md").write_text(md, encoding="utf-8")


def print_summary(metrics: AggregateMetrics) -> None:
    """终端打印汇总表格。"""
    print("\n" + "=" * 50)
    print("  AutoPatch Evaluation Summary")
    print("=" * 50)
    print(f"  Total Instances     : {metrics.total_instances}")
    print(f"  Resolved            : {metrics.resolved}")
    print(f"  Partially Resolved  : {metrics.partially_resolved}")
    print(f"  Failed              : {metrics.failed}")
    print(f"  Errors              : {metrics.errors}")
    print(f"  Timeouts            : {metrics.timeouts}")
    print(f"  Resolve Rate        : {metrics.resolve_rate:.1%}")
    print(f"  Avg Steps           : {metrics.avg_step_count:.1f}")
    print(f"  Avg Time (s)        : {metrics.avg_elapsed_seconds:.1f}")
    print(f"  Median Time (s)     : {metrics.median_elapsed_seconds:.1f}")

    if metrics.by_repo:
        print("\n  By Repository:")
        for repo, rm in sorted(metrics.by_repo.items()):
            print(f"    {repo:40s} {rm.resolved}/{rm.total} ({rm.resolve_rate:.0%})")
    print("=" * 50)


# ── 内部 ──

def _build_markdown_report(metrics: AggregateMetrics, run_id: str) -> str:
    lines = [
        "# AutoPatch Evaluation Report",
        "",
        f"Run ID: {run_id}",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total Instances | {metrics.total_instances} |",
        f"| Resolved | {metrics.resolved} |",
        f"| Partially Resolved | {metrics.partially_resolved} |",
        f"| Failed | {metrics.failed} |",
        f"| Errors | {metrics.errors} |",
        f"| Timeouts | {metrics.timeouts} |",
        f"| **Resolve Rate** | **{metrics.resolve_rate:.1%}** |",
        f"| Avg Steps | {metrics.avg_step_count:.1f} |",
        f"| Avg Time (s) | {metrics.avg_elapsed_seconds:.1f} |",
        f"| Median Time (s) | {metrics.median_elapsed_seconds:.1f} |",
        "",
    ]

    if metrics.by_repo:
        lines += [
            "## By Repository",
            "",
            "| Repository | Total | Resolved | Rate |",
            "|---|---|---|---|",
        ]
        for repo, rm in sorted(metrics.by_repo.items()):
            lines.append(f"| {repo} | {rm.total} | {rm.resolved} | {rm.resolve_rate:.0%} |")
        lines.append("")

    return "\n".join(lines)
