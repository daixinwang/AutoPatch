"""
task_store.py
-------------
AutoPatch 任务元数据持久化模块。

每个任务（一次 /api/patch 调用）在 tasks/{task_id}.json 中保存以下信息：
  - task_id       : 全局唯一 UUID
  - repo_url      : 仓库地址（"owner/repo" 或完整 URL）
  - issue_number  : Issue 编号
  - workspace_path: 本地 clone 目录（中断时保留，恢复时复用）
  - repo_language : 仓库主要编程语言
  - issue_text    : Issue 完整文本（恢复时重建 initial_state 用）
  - status        : running | interrupted | completed | failed
  - created_at    : ISO 8601 创建时间
  - updated_at    : ISO 8601 最后更新时间
"""

import json
import logging
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

TASKS_DIR = Path("tasks")

TaskStatus = Literal["running", "interrupted", "completed", "failed"]


@dataclass
class TaskRecord:
    task_id: str
    repo_url: str
    issue_number: int
    workspace_path: str
    repo_language: str
    issue_text: str
    status: TaskStatus
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRecord":
        return cls(**data)


class TaskStore:
    """JSON 文件形式的任务元数据存储。线程安全（每次操作均原子读写）。"""

    def __init__(self, tasks_dir: Path = TASKS_DIR) -> None:
        self._dir = tasks_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── 写操作 ──────────────────────────────────────────────

    def create(
        self,
        repo_url: str,
        issue_number: int,
        workspace_path: str,
        repo_language: str,
        issue_text: str,
        task_id: Optional[str] = None,
    ) -> TaskRecord:
        """新建任务记录，初始状态为 running。

        Args:
            task_id: 可选，指定任务 ID；不传时自动生成 UUID。
        """
        now = datetime.now(timezone.utc).isoformat()
        record = TaskRecord(
            task_id=task_id or str(uuid.uuid4()),
            repo_url=repo_url,
            issue_number=issue_number,
            workspace_path=workspace_path,
            repo_language=repo_language,
            issue_text=issue_text,
            status="running",
            created_at=now,
            updated_at=now,
        )
        self._save(record)
        return record

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        """更新任务状态。task_id 不存在时静默忽略。"""
        record = self.get(task_id)
        if record is None:
            return
        record.status = status
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(record)

    def delete(self, task_id: str, remove_workspace: bool = True) -> bool:
        """删除任务记录，可选同时删除 workspace 目录。返回是否删除成功。"""
        record = self.get(task_id)
        if record is None:
            return False
        if remove_workspace:
            ws = Path(record.workspace_path).resolve()
            tmp_root = Path(tempfile.gettempdir()).resolve()
            if ws.is_relative_to(tmp_root) and ws.exists():
                shutil.rmtree(ws, ignore_errors=True)
        path = self._path(task_id)
        path.unlink(missing_ok=True)
        return True

    # ── 读操作 ──────────────────────────────────────────────

    def get(self, task_id: str) -> Optional[TaskRecord]:
        """按 task_id 查询，不存在返回 None。"""
        path = self._path(task_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return TaskRecord.from_dict(json.load(f))

    def list_all(self) -> list[TaskRecord]:
        """返回所有任务，按创建时间降序。"""
        records = []
        for path in self._dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    records.append(TaskRecord.from_dict(json.load(f)))
            except Exception:
                logger.warning("跳过损坏的任务文件: %s", path, exc_info=True)
                continue
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    # ── 内部工具 ────────────────────────────────────────────

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        """校验 task_id 为合法 UUID 格式，防止路径注入。"""
        if not _UUID_RE.match(task_id):
            raise ValueError(f"非法 task_id（必须为 UUID 格式）: {task_id!r}")

    def _path(self, task_id: str) -> Path:
        self._validate_task_id(task_id)
        return self._dir / f"{task_id}.json"

    def _save(self, record: TaskRecord) -> None:
        path = self._path(record.task_id)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
        tmp.replace(path)  # 原子替换，避免写入一半时被读取
