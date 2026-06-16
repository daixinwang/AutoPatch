"""
tests/test_api_events.py
------------------------
Unit tests for API streaming event formatting helpers.
"""

import json

from api.events import log_event, node_event, result_event, sse_event, task_event, token_event


def test_sse_event_serializes_json_payload():
    assert sse_event({"type": "done"}) == 'data: {"type": "done"}\n\n'


def test_log_event_includes_level_node_and_message():
    raw = log_event("Planning started", level="system", node="Planner")

    assert raw.startswith("data: ")
    payload = json.loads(raw.removeprefix("data: ").strip())
    assert payload == {
        "type": "log",
        "level": "system",
        "node": "Planner",
        "message": "Planning started",
    }


def test_node_event_formats_status_updates():
    payload = json.loads(node_event("coder", "running", "editing").removeprefix("data: ").strip())
    assert payload == {
        "type": "node",
        "node": "coder",
        "status": "running",
        "detail": "editing",
    }


def test_token_task_and_result_events_keep_existing_schema():
    token_payload = json.loads(token_event("coder", "abc").removeprefix("data: ").strip())
    task_payload = json.loads(task_event("task-1", "new").removeprefix("data: ").strip())
    result_payload = json.loads(
        result_event("diff", "PASS", 3, ["a.py"]).removeprefix("data: ").strip()
    )

    assert token_payload == {"type": "token", "node": "coder", "content": "abc"}
    assert task_payload == {"type": "task", "taskId": "task-1", "status": "new"}
    assert result_payload == {
        "type": "result",
        "diff": "diff",
        "reviewResult": "PASS",
        "stepCount": 3,
        "changedFiles": ["a.py"],
    }
