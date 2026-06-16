"""
tests/test_api_auth.py
----------------------
Unit tests for API bearer-token authentication dependency.
"""

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from typing import Optional

from api.auth import set_api_key_for_testing, verify_api_key


@pytest.fixture(autouse=True)
def _reset_api_key():
    set_api_key_for_testing("")
    yield
    set_api_key_for_testing("")


def _request_with_auth(value: Optional[str]) -> Request:
    headers = []
    if value is not None:
        headers.append((b"authorization", value.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


@pytest.mark.asyncio
async def test_verify_api_key_allows_requests_when_key_is_unconfigured():
    set_api_key_for_testing("")

    await verify_api_key(_request_with_auth(None))


@pytest.mark.asyncio
async def test_verify_api_key_rejects_missing_or_invalid_bearer_token():
    set_api_key_for_testing("secret")

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(_request_with_auth(None))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "未授权：无效的 API Key"

    with pytest.raises(HTTPException) as invalid_exc:
        await verify_api_key(_request_with_auth("Bearer wrong"))
    assert invalid_exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_allows_valid_bearer_token():
    set_api_key_for_testing("secret")

    await verify_api_key(_request_with_auth("Bearer secret"))
