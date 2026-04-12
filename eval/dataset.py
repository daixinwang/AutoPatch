"""
eval/dataset.py
---------------
SWE-bench 数据集加载与过滤。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from eval.config import EvalConfig


@dataclass
class SWEBenchInstance:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    test_patch: str
    patch: str  # gold patch (参考用)
    fail_to_pass: List[str]
    pass_to_pass: List[str]
    version: Optional[str] = None
    environment_setup_commit: Optional[str] = None


def load_dataset(config: EvalConfig) -> List[SWEBenchInstance]:
    """
    从 HuggingFace datasets 或本地 JSON 加载 SWE-bench 数据集。
    """
    raw_items = _load_raw(config.dataset_name, config.dataset_split)
    instances = [_parse_item(item) for item in raw_items]
    instances = _filter(instances, config)

    if config.shuffle:
        random.seed(config.seed)
        random.shuffle(instances)

    if config.max_instances is not None:
        instances = instances[: config.max_instances]

    return instances


def _load_raw(dataset_name: str, split: str) -> list:
    """加载原始数据：先尝试 HuggingFace datasets，回退到本地 JSON。"""
    path = Path(dataset_name)
    if path.exists() and path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))

    try:
        from datasets import load_dataset as hf_load
        ds = hf_load(dataset_name, split=split)
        return list(ds)
    except Exception as e:
        raise RuntimeError(
            f"无法加载数据集 '{dataset_name}': {e}\n"
            "请安装 datasets 库: pip install datasets"
        ) from e


def _parse_item(item: dict) -> SWEBenchInstance:
    """将原始 dict 解析为 SWEBenchInstance。"""

    def _parse_list(val) -> List[str]:
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else [str(parsed)]
            except json.JSONDecodeError:
                return [val] if val.strip() else []
        return []

    return SWEBenchInstance(
        instance_id=item["instance_id"],
        repo=item["repo"],
        base_commit=item["base_commit"],
        problem_statement=item["problem_statement"],
        test_patch=item.get("test_patch", ""),
        patch=item.get("patch", ""),
        fail_to_pass=_parse_list(item.get("FAIL_TO_PASS", [])),
        pass_to_pass=_parse_list(item.get("PASS_TO_PASS", [])),
        version=item.get("version"),
        environment_setup_commit=item.get("environment_setup_commit"),
    )


def _filter(instances: List[SWEBenchInstance], config: EvalConfig) -> List[SWEBenchInstance]:
    """按 instance_ids / repos 过滤。"""
    if config.instance_ids:
        id_set = set(config.instance_ids)
        instances = [i for i in instances if i.instance_id in id_set]

    if config.repos:
        repo_set = set(config.repos)
        instances = [i for i in instances if i.repo in repo_set]

    return instances
