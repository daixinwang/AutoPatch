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
MAX_CODER_STEPS: int = int(os.getenv("MAX_CODER_STEPS", "40"))
# LangGraph 递归深度限制
RECURSION_LIMIT: int = int(os.getenv("RECURSION_LIMIT", "500"))

# ── LLM ──────────────────────────────────────────────────
# 各 Agent 专属模型，可通过同名环境变量覆盖。
PLANNER_MODEL_NAME:     str = os.getenv("PLANNER_MODEL_NAME",     "claude-haiku-4-5-20251001")
CODER_MODEL_NAME:       str = os.getenv("CODER_MODEL_NAME",       "claude-sonnet-4-6")
TEST_RUNNER_MODEL_NAME: str = os.getenv("TEST_RUNNER_MODEL_NAME", "claude-haiku-4-5-20251001")
REVIEWER_MODEL_NAME:    str = os.getenv("REVIEWER_MODEL_NAME",    "claude-sonnet-4-6")

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

# ── LLM Context 水位线（token 数，基于 cl100k_base 编码）────
# 70% 水位：记录 warning + 在 coder_node 追加收尾提示，引导模型尽快完成
WARN_TOKEN_LIMIT: int     = int(os.getenv("WARN_TOKEN_LIMIT",     "40000"))
# 85% 水位：执行 _compress_messages() 压缩 + 追加收尾提示
COMPRESS_TOKEN_LIMIT: int = int(os.getenv("COMPRESS_TOKEN_LIMIT", "50000"))
# 100% 水位：跳过本次 coder_node LLM 调用，直接推进到 test_runner_node
MAX_TOKEN_LIMIT: int      = int(os.getenv("MAX_TOKEN_LIMIT",      "60000"))
# Reviewer 内部循环允许的工具调用总数（防止失控）。
MAX_REVIEWER_TOOL_CALLS: int = int(os.getenv("MAX_REVIEWER_TOOL_CALLS", "8"))

# ── 代码 RAG 配置 ──────────────────────────────────────────
# 是否启用代码 RAG；关闭后不会构建索引，也不会暴露 semantic_search_codebase 工具。
AUTOPATCH_RAG_ENABLED: bool = os.getenv("AUTOPATCH_RAG_ENABLED", "true").lower() == "true"
# Embedding 模型（OpenAI text-embedding-3-small）
RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
# Embedding 向量维度；0 表示不显式传递 dimensions 参数。
RAG_EMBEDDING_DIMENSIONS: int = int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "0") or "0")
# RAG 索引缓存根目录
RAG_CACHE_DIR: str = os.getenv("RAG_CACHE_DIR", ".autopatch_cache")
# OpenAI Embedding 专属 API Key（与 Anthropic 代理的 OPENAI_API_KEY 分开）
OPENAI_EMBED_API_KEY: str = os.getenv("OPENAI_EMBED_API_KEY", os.getenv("OPENAI_API_KEY", ""))
# OpenAI Embedding API Base URL（默认为官方端点）
OPENAI_EMBED_BASE_URL: str = os.getenv("OPENAI_EMBED_BASE_URL", "")
# P1: Cross-Encoder Rerank（默认关闭，通过环境变量启用）
AUTOPATCH_RAG_RERANK: bool = os.getenv("AUTOPATCH_RAG_RERANK", "false").lower() == "true"


def validate_required_env() -> None:
    """校验必需的环境变量，缺失时抛出明确错误。"""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "环境变量 OPENAI_API_KEY 未设置。请在 .env 文件或系统环境中配置。"
        )
