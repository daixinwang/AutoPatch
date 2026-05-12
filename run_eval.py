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

import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from eval.config import EvalConfig
from eval.runner import EvalRunner

logger = logging.getLogger(__name__)


def main() -> int:
    config = EvalConfig.from_cli()

    # 环境检查
    _check_env(config)

    logger.info("=" * 50)
    logger.info("  AutoPatch SWE-bench Evaluation")
    logger.info("=" * 50)
    logger.info(f"  Dataset       : {config.dataset_name}")
    logger.info(f"  Max Instances : {config.max_instances or 'all'}")
    logger.info(f"  Concurrency   : {config.concurrency}")
    logger.info(f"  Timeout/inst  : {config.timeout_per_instance}s")
    logger.info(f"  Results Dir   : {config.results_dir}")
    logger.info(f"  Resume        : {config.resume}")
    logger.info("=" * 50)

    runner = EvalRunner(config)
    metrics = runner.run()

    return 0 if metrics.total_instances > 0 else 1


def _check_env(config=None) -> None:
    """检查必要的环境变量和依赖。"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    missing = []
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    if missing:
        logger.error(f"[Error] 缺少环境变量: {', '.join(missing)}")
        logger.error("请设置后重试（可在 .env 文件中配置）")
        sys.exit(1)

    try:
        import datasets  # noqa: F401
    except ImportError:
        logger.error("[Error] 缺少 datasets 库，请安装: pip install datasets")
        sys.exit(1)

    # Docker 模式下检查 Docker 是否可用
    if config is not None and config.use_docker:
        import subprocess as _sp
        try:
            r = _sp.run(["docker", "info"], capture_output=True, timeout=10)
        except _sp.TimeoutExpired:
            logger.error("[Error] docker info 超时，Docker Desktop 可能正在启动中")
            sys.exit(1)
        if r.returncode != 0:
            logger.error(
                "[Error] Docker 未启动或未安装，--docker 模式需要 Docker Desktop 运行"
            )
            sys.exit(1)
        logger.info("[OK] Docker 可用")


if __name__ == "__main__":
    sys.exit(main())
