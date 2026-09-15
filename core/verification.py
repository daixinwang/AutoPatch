"""Server-side verification receipts, bound to exact repo/issue/diff content."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from agent.models import verified


def receipt_path(repo, issue, patch, directory):
    digest = hashlib.sha256(json.dumps([repo, issue, patch], ensure_ascii=False).encode()).hexdigest()
    return Path(directory) / (digest + ".json")


def save_verification(repo, issue, patch, state, directory="tasks/verification", *, base_commit=None):
    path = receipt_path(repo, issue, patch, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {key: state.get(key) for key in ("terminal_status", "test_report", "review_decision")}
    data["base_commit"] = base_commit
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def is_verified(repo, issue, patch, directory="tasks/verification", *, base_commit=None):
    try:
        data = json.loads(receipt_path(repo, issue, patch, directory).read_text(encoding="utf-8"))
        return verified(data) and (base_commit is None or data.get("base_commit") == base_commit)
    except (OSError, ValueError):
        return False
