"""
api/auth.py
-----------
Bearer-token authentication dependency for protected API endpoints.
"""

import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("AUTOPATCH_API_KEY", "")
if not _API_KEY:
    logger.warning("AUTOPATCH_API_KEY 未设置，API 端点无认证保护（仅限开发环境）")


def set_api_key_for_testing(api_key: str) -> None:
    """Override the module-level API key in tests."""
    global _API_KEY
    _API_KEY = api_key


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency: validate Authorization: Bearer <key>."""
    if not _API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _API_KEY:
        raise HTTPException(status_code=401, detail="未授权：无效的 API Key")
