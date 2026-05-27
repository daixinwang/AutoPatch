"""
_estimate_messages_tokens 的单元测试。

直接从 agent.graph 导入私有函数（测试内部实现是可接受的，
因为这是一个关键的成本控制函数，需要确保行为正确）。
"""
import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from agent.graph import _estimate_messages_tokens


def test_empty_list_returns_zero():
    assert _estimate_messages_tokens([]) == 0


def test_single_string_message():
    msgs = [HumanMessage(content="hello world")]
    count = _estimate_messages_tokens(msgs)
    # "hello world" 用 cl100k_base 编码为 2 个 token
    assert count == 2


def test_multiple_messages_summed():
    msgs = [
        HumanMessage(content="hello"),   # 1 token
        AIMessage(content="world"),      # 1 token
    ]
    assert _estimate_messages_tokens(msgs) == 2


def test_empty_content_counts_zero():
    msgs = [HumanMessage(content=""), SystemMessage(content="")]
    assert _estimate_messages_tokens(msgs) == 0


def test_anthropic_list_content_extracted():
    """Anthropic 多 block content（list 格式）应正确提取 text 并计数。"""
    msgs = [AIMessage(content=[
        {"type": "text", "text": "hello"},
        {"type": "tool_use", "id": "x", "name": "fn", "input": {}},
    ])]
    count = _estimate_messages_tokens(msgs)
    # 只提取 text block，tool_use block 被跳过
    assert count == 1  # "hello" = 1 token


def test_none_content_counts_zero():
    # langchain_core (pydantic v2) rejects None at construction time,
    # so we use a plain object to directly exercise the None guard in our function.
    class _FakeMsg:
        content = None

    assert _estimate_messages_tokens([_FakeMsg()]) == 0
