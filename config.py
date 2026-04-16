"""
config.py
---------
集中配置管理。所有可配置的常量从此模块导入。

每个值都支持通过同名环境变量覆盖，未设置时使用默认值。
"""

import os

# ── Agent 参数 ───────────────────────────────────────────
# Reviewer 最多打回次数
MAX_REVIEW_RETRIES: int = int(os.getenv("MAX_REVIEW_RETRIES", "3"))
# Coder→Tool 单轮最多循环次数
MAX_CODER_STEPS: int = int(os.getenv("MAX_CODER_STEPS", "25"))
# LangGraph 递归深度限制
RECURSION_LIMIT: int = int(os.getenv("RECURSION_LIMIT", "100"))

# ── LLM ──────────────────────────────────────────────────
OPENAI_MODEL_NAME: str = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")

# ── 服务器 ───────────────────────────────────────────────
MAX_CONCURRENT_PATCHES: int = int(os.getenv("MAX_CONCURRENT_PATCHES", "3"))
DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

# ── 工具执行 ─────────────────────────────────────────────
DEFAULT_TIMEOUT_SECONDS: int = int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "30"))
MAX_TIMEOUT_SECONDS: int = int(os.getenv("MAX_TIMEOUT_SECONDS", "120"))
MAX_OUTPUT_BYTES: int = int(os.getenv("MAX_OUTPUT_BYTES", "8000"))


def validate_required_env() -> None:
    """校验必需的环境变量，缺失时抛出明确错误。"""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "环境变量 OPENAI_API_KEY 未设置。请在 .env 文件或系统环境中配置。"
        )
