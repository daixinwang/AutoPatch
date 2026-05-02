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

# ── GitHub HTTP 重试 ─────────────────────────────────────
# 网络抖动 / 5xx / 429（限速）时重试，4xx（除 429）不重试。
GITHUB_RETRY_MAX_ATTEMPTS: int = int(os.getenv("GITHUB_RETRY_MAX_ATTEMPTS", "3"))
GITHUB_RETRY_BACKOFF_BASE: float = float(os.getenv("GITHUB_RETRY_BACKOFF_BASE", "1.0"))

# ── LLM Context 控制 ─────────────────────────────────────
# Coder 进入节点时如果 messages 总字符数超过此阈值，触发硬压缩（保留 Issue + 各 Agent 摘要消息）。
MAX_MESSAGE_CHARS: int = int(os.getenv("MAX_MESSAGE_CHARS", "60000"))
# Reviewer 内部循环允许的工具调用总数（防止失控）。
MAX_REVIEWER_TOOL_CALLS: int = int(os.getenv("MAX_REVIEWER_TOOL_CALLS", "8"))


def validate_required_env() -> None:
    """校验必需的环境变量，缺失时抛出明确错误。"""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "环境变量 OPENAI_API_KEY 未设置。请在 .env 文件或系统环境中配置。"
        )
