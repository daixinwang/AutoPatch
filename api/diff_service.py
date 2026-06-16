"""
api/diff_service.py
-------------------
Diff generation and persistence helpers for API pipelines.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from core.diff_generator import generate_diff, get_changed_files, write_diff_file

logger = logging.getLogger(__name__)


async def generate_and_save_diff(
    tmp_dir: str,
    issue_number: int,
    repo_url: str,
    review_result: str,
) -> tuple[str, list[str]]:
    """Generate a diff, save it when non-empty, and return changed file paths."""
    loop = asyncio.get_running_loop()

    try:
        diff_content = await loop.run_in_executor(None, generate_diff, tmp_dir)
    except RuntimeError as e:
        diff_content = ""
        logger.warning("Diff 生成失败: %s", e)

    changed_files_raw = await loop.run_in_executor(None, get_changed_files, tmp_dir)
    changed_files = [c["path"] for c in changed_files_raw]

    if diff_content.strip():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        diff_path = Path("patches") / f"issue-{issue_number}_{ts}.diff"
        await loop.run_in_executor(
            None, write_diff_file, diff_content, diff_path,
            repo_url, issue_number, review_result,
        )
        logger.info("Diff 已保存: %s", diff_path)

    return diff_content, changed_files
