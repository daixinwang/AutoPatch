"""
api/events.py
-------------
SSE event formatting helpers shared by API streaming endpoints.
"""

import json
from typing import Optional


def sse_event(data: dict) -> str:
    """Serialize a JSON payload as a Server-Sent Events data frame."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def log_event(message: str, level: str = "info", node: Optional[str] = None) -> str:
    return sse_event({"type": "log", "level": level, "node": node, "message": message})


def node_event(node_id: str, status: str, detail: str = "") -> str:
    return sse_event({"type": "node", "node": node_id, "status": status, "detail": detail})


def token_event(node_id: str, content: str) -> str:
    return sse_event({"type": "token", "node": node_id, "content": content})


def task_event(task_id: str, status: str) -> str:
    return sse_event({"type": "task", "taskId": task_id, "status": status})


def result_event(diff: str, review_result: str, step_count: int, changed_files: list) -> str:
    return sse_event({
        "type": "result",
        "diff": diff,
        "reviewResult": review_result,
        "stepCount": step_count,
        "changedFiles": changed_files,
    })
