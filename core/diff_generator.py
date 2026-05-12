"""
diff_generator.py
-----------------
Git diff 生成器。

职责：
  1. 在 Agent 修改文件后，通过 git diff 生成标准 unified diff 格式
  2. 处理新建文件（git 未追踪文件）和修改文件两种情况
  3. 将 diff 内容写入 .diff 文件，方便人工审查或直接 git apply

注意：
  - 生成的 diff 仅反映从 clone 到 Agent 修改之间的变化
  - 新建文件使用 git diff --cached（先 add 再 diff --cached）
"""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Union

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# diff 生成核心函数
# ══════════════════════════════════════════════

def generate_diff(repo_path: Union[str, Path]) -> str:
    """
    在指定 git 仓库目录中生成完整的 unified diff。

    同时处理：
      - 已追踪文件的修改（git diff HEAD）
      - 未追踪的新建文件（git add -N + git diff）

    Args:
        repo_path: 本地 git 仓库根目录路径

    Returns:
        完整的 unified diff 字符串；若无变化返回空字符串

    Raises:
        RuntimeError: git 命令执行失败时抛出
    """
    repo = Path(repo_path).resolve()

    if not (repo / ".git").exists():
        raise RuntimeError(f"路径 {repo} 不是一个 git 仓库（找不到 .git 目录）")

    logger.info(f"  [DiffGenerator] 在 {repo} 中生成 diff...")

    # ── Step 1: 将未追踪的新文件加入 index（intent-to-add），使其出现在 diff 中
    _stage_new_files(repo)

    # ── Step 2: 生成 diff（包含已修改文件和 intent-to-add 的新文件）
    diff_content = _run_git_diff(repo)

    if not diff_content.strip():
        logger.warning("  [DiffGenerator] ⚠️  未检测到任何文件变化")
        return ""

    line_count = diff_content.count("\n")
    file_count = diff_content.count("\ndiff --git") + (1 if diff_content.startswith("diff --git") else 0)
    logger.info(f"  [DiffGenerator] ✅ 生成 diff：{file_count} 个文件，{line_count} 行")
    return diff_content


def _stage_new_files(repo: Path) -> None:
    """
    将工作区中所有未追踪文件标记为 intent-to-add（git add -N）。
    这样 git diff 才能显示新文件的内容，而不是将其视为未追踪文件跳过。

    Args:
        repo: git 仓库根目录
    """
    # 获取未追踪文件列表
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    untracked = [f.strip() for f in result.stdout.splitlines() if f.strip()]

    if untracked:
        logger.debug(f"  [DiffGenerator] 发现 {len(untracked)} 个新文件，标记为 intent-to-add: {untracked}")
        subprocess.run(
            ["git", "add", "-N"] + untracked,
            cwd=str(repo),
            capture_output=True,
        )


def _run_git_diff(repo: Path) -> str:
    """
    执行 git diff HEAD 获取所有变更（已追踪的修改 + intent-to-add 的新文件）。

    Args:
        repo: git 仓库根目录

    Returns:
        diff 字符串
    """
    result = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff 失败: {result.stderr}")
    return result.stdout


def get_changed_files(repo_path: Union[str, Path]) -> List[Dict]:
    """
    获取工作区变更文件的摘要列表。

    Args:
        repo_path: git 仓库根目录

    Returns:
        变更文件列表，每项包含 status（M/A/D）和 path 字段
    """
    repo = Path(repo_path).resolve()
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    changes = []
    for line in result.stdout.splitlines():
        if len(line) >= 3:
            status_code = line[:2].strip()
            file_path = line[3:].strip()
            status_map = {
                "M": "modified", "A": "added", "D": "deleted",
                "R": "renamed",  "C": "copied", "?": "untracked",
            }
            status = status_map.get(status_code[0], status_code)
            changes.append({"status": status, "path": file_path})
    return changes


# ══════════════════════════════════════════════
# diff 文件写入
# ══════════════════════════════════════════════

def write_diff_file(
    diff_content: str,
    output_path: Union[str, Path],
    repo_url: str = "",
    issue_number: int = 0,
    review_result: str = "",
) -> Path:
    """
    将 diff 内容写入 .diff 文件，并在文件头部附加元数据注释。

    Args:
        diff_content:  git diff 生成的 unified diff 字符串
        output_path:   输出文件路径（如 patches/issue-42.diff）
        repo_url:      来源仓库 URL（写入注释）
        issue_number:  对应的 Issue 编号（写入注释）
        review_result: Reviewer 的评审结论（写入注释）

    Returns:
        写入的文件 Path 对象
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header_lines = [
        f"# AutoPatch Generated Diff",
        f"# Generated at : {timestamp}",
    ]
    if repo_url:
        header_lines.append(f"# Repository   : {repo_url}")
    if issue_number:
        header_lines.append(f"# Issue        : #{issue_number}")
    if review_result:
        # 单行化评审结论
        review_oneline = review_result.replace("\n", " | ")[:120]
        header_lines.append(f"# Review Result: {review_oneline}")
    header_lines.append(f"# Apply with   : git apply {output.name}")
    header_lines.append("")  # 空行分隔注释和 diff 内容

    full_content = "\n".join(header_lines) + diff_content

    output.write_text(full_content, encoding="utf-8")
    logger.info(f"✅ [DiffGenerator] Diff 文件已写入: {output}")
    logger.debug(f"   大小: {output.stat().st_size} bytes，路径: {output.resolve()}")
    return output


def print_diff_summary(diff_content: str) -> None:
    """
    在终端打印 diff 的简要摘要（变更文件和增删行数统计）。

    Args:
        diff_content: unified diff 字符串
    """
    if not diff_content.strip():
        logger.info("  （无变更）")
        return

    added = diff_content.count("\n+") - diff_content.count("\n+++")
    removed = diff_content.count("\n-") - diff_content.count("\n---")

    # 提取变更的文件名
    changed_files = re.findall(r"^diff --git a/(.+?) b/", diff_content, re.MULTILINE)

    logger.info(f"📊 Diff 摘要:")
    logger.info(f"   变更文件数 : {len(changed_files)}")
    logger.info(f"   新增行数   : +{added}")
    logger.info(f"   删除行数   : -{removed}")
    if changed_files:
        logger.info(f"   变更文件   :")
        for f in changed_files:
            logger.info(f"     • {f}")


def filter_diff(diff: str, exclude_paths: Set[str]) -> str:
    """
    从 unified diff 字符串中过滤掉指定文件的 diff 块。

    用于从 agent_patch 中剔除由评测框架（test_patch）引入的测试文件改动，
    确保 agent_patch 只包含 Agent 实际修改的内容。

    Args:
        diff:          unified diff 字符串（git diff HEAD 的输出）
        exclude_paths: 需要排除的文件路径集合（相对于仓库根目录，如 "tests/test_foo.py"）

    Returns:
        过滤后的 diff 字符串；若无剩余块则返回空字符串
    """
    if not diff or not exclude_paths:
        return diff or ""

    blocks = re.split(r"(?=^diff --git )", diff, flags=re.MULTILINE)
    result = []
    for block in blocks:
        if not block.strip():
            continue
        m = re.match(r"^diff --git a/(.+?) b/", block)
        if m and m.group(1) in exclude_paths:
            continue
        result.append(block)
    return "".join(result)
