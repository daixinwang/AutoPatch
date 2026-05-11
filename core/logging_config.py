"""
logging_config.py
-----------------
全局日志配置。所有模块应使用 logging.getLogger(__name__) 取代 print()。

日志级别通过环境变量 LOG_LEVEL 控制（默认 INFO）。
"""

import logging
import os
import sys


def setup_logging() -> None:
    """配置全局日志格式和级别。应在应用启动时调用一次。"""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler
    if not root.handlers:
        root.addHandler(handler)
