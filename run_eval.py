#!/usr/bin/env python3
"""
run_eval.py
-----------
AutoPatch SWE-bench 评测 CLI 入口。

用法:
    # 快速验证 5 条 (指定 repo)
    python run_eval.py --max-instances 5 --repos sympy/sympy

    # 30 条小规模评测
    python run_eval.py --max-instances 30 --timeout 600

    # 续跑中断的评测
    python run_eval.py --run-id 20260412_143000 --resume

    # 指定实例
    python run_eval.py --instance-ids sympy__sympy-20154 django__django-12345

    # 并行执行
    python run_eval.py --concurrency 2 --max-instances 30
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from eval.config import EvalConfig
from eval.runner import EvalRunner


def main() -> int:
    config = EvalConfig.from_cli()

    # 环境检查
    _check_env()

    print("=" * 50)
    print("  AutoPatch SWE-bench Evaluation")
    print("=" * 50)
    print(f"  Dataset       : {config.dataset_name}")
    print(f"  Max Instances : {config.max_instances or 'all'}")
    print(f"  Concurrency   : {config.concurrency}")
    print(f"  Timeout/inst  : {config.timeout_per_instance}s")
    print(f"  Results Dir   : {config.results_dir}")
    print(f"  Resume        : {config.resume}")
    print("=" * 50)

    runner = EvalRunner(config)
    metrics = runner.run()

    return 0 if metrics.total_instances > 0 else 1


def _check_env() -> None:
    """检查必要的环境变量和依赖。"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    missing = []
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    if missing:
        print(f"[Error] 缺少环境变量: {', '.join(missing)}")
        print("请设置后重试（可在 .env 文件中配置）")
        sys.exit(1)

    try:
        import datasets  # noqa: F401
    except ImportError:
        print("[Error] 缺少 datasets 库，请安装: pip install datasets")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
