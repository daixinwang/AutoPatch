"""
autopatch.py
------------
AutoPatch 完整应用入口。

功能流程：
  1. 解析命令行参数（GitHub URL + Issue Number）
  2. 调用 GitHub API 拉取 Issue 内容
  3. 将目标仓库 clone 到本地临时目录
  4. 以 clone 目录为工作区，运行多 Agent 流水线修复 Bug
  5. 生成 git diff，写入 .diff 文件
  6. 打印完整摘要报告

用法：
    python autopatch.py <repo_url> <issue_number> [选项]

示例：
    # 基本用法
    python autopatch.py https://github.com/owner/repo 42

    # 指定输出目录和分支
    python autopatch.py owner/repo 42 --output-dir ./patches --branch main

    # 不自动清理 clone 目录（方便调试）
    python autopatch.py owner/repo 42 --keep-workspace

    # 使用本地已有目录（跳过 clone）
    python autopatch.py owner/repo 42 --workspace-dir /path/to/local/repo
"""

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import logging

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from core.logging_config import setup_logging

logger = logging.getLogger(__name__)

# 加载 .env
load_dotenv()

# 本地模块
from core.github_client import GitHubClient, RepoWorkspace, parse_github_url
from core.diff_generator import (
    generate_diff,
    get_changed_files,
    print_diff_summary,
    write_diff_file,
)
from agent.graph import app, AgentState, APP_CONFIG
from tools.workspace import set_workspace, reset_workspace


# ══════════════════════════════════════════════
# CLI 参数定义
# ══════════════════════════════════════════════

def build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="autopatch",
        description="AutoPatch — 基于 LangGraph 多 Agent 的 GitHub Issue 自动修复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python autopatch.py https://github.com/psf/requests 1234
  python autopatch.py psf/requests 1234 --output-dir ./patches
  python autopatch.py psf/requests 1234 --workspace-dir /tmp/requests --keep-workspace
        """,
    )

    parser.add_argument(
        "repo_url",
        help="GitHub 仓库 URL 或 owner/repo 格式，例如：https://github.com/owner/repo 或 owner/repo",
    )
    parser.add_argument(
        "issue_number",
        type=int,
        help="要修复的 GitHub Issue 编号，例如：42",
    )
    parser.add_argument(
        "--output-dir",
        default="./patches",
        metavar="DIR",
        help="diff 文件输出目录（默认：./patches）",
    )
    parser.add_argument(
        "--branch",
        default=None,
        metavar="BRANCH",
        help="clone 指定分支（默认：仓库的默认分支）",
    )
    parser.add_argument(
        "--workspace-dir",
        default=None,
        metavar="DIR",
        help="使用已有本地目录作为工作区（跳过 clone 步骤，方便调试）",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="运行结束后保留 clone 的临时目录（默认自动删除）",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="拉取 Issue 时跳过评论（加快速度）",
    )
    return parser


# ══════════════════════════════════════════════
# Agent 运行（可复用）
# ══════════════════════════════════════════════

def run_agent_on_issue(
    issue_text: str,
    working_dir: str,
    repo_language: str = "Unknown",
) -> dict:
    """
    以指定目录为工作区，运行多 Agent 流水线处理 Issue。

    Agent 内部的文件操作工具（read_file / write_file / search 等）
    都使用相对路径，而 working_dir 通过 ContextVar 传递给工具，
    从而让工具操作目标仓库文件而非 AutoPatch 自身的文件。

    Args:
        issue_text:  格式化后的 Issue 描述文本（来自 GitHubIssue.to_prompt_text()）
        working_dir: Agent 的工作目录（目标仓库 clone 路径）

    Returns:
        包含 final_output / review_result / step_count 的结果字典
    """
    # 设置工作目录（不修改全局 CWD，通过 ContextVar 传递给工具）
    _ws_token = set_workspace(working_dir)
    logger.info(f"📂 [AutoPatch] 工作目录已设置: {working_dir}")

    try:
        initial_state: AgentState = {
            "messages":      [HumanMessage(content=f"Issue 需求：\n\n{issue_text}")],
            "issue_task":    issue_text,
            "repo_language": repo_language,
            "plan":          "",
            "test_output":   "",
            "review_result": "",
            "review_retries": 0,
        }

        NODE_ICONS = {
            "planner_node":     "📋 Planner",
            "coder_node":       "💻 Coder",
            "tool_node":        "🔧 Tools",
            "test_runner_node": "🧪 TestRunner",
            "reviewer_node":    "🔍 Reviewer",
        }

        step_count = 0
        final_output = ""
        review_result = ""

        logger.info("▶️  Agent 流水线启动 (stream 模式)...")

        for chunk in app.stream(initial_state, config=APP_CONFIG, stream_mode="updates"):
            step_count += 1

            for node_name, node_output in chunk.items():
                icon = NODE_ICONS.get(node_name, f"[{node_name}]")
                logger.info(f"[Step {step_count}] {icon}")

                if "plan" in node_output and node_output["plan"]:
                    preview = node_output["plan"][:120].replace("\n", " ")
                    logger.debug(f"  📝 plan: {preview}...")

                if "test_output" in node_output and node_output["test_output"]:
                    key_lines = [
                        l for l in node_output["test_output"].splitlines()
                        if any(kw in l.upper() for kw in ["PASS", "FAIL", "ERROR", "EXIT", "OK"])
                    ]
                    summary = " | ".join(key_lines[:3]) if key_lines else node_output["test_output"][:80]
                    logger.debug(f"  🧪 test: {summary}")

                if "review_result" in node_output and node_output["review_result"]:
                    review_result = node_output["review_result"]
                    logger.debug(f"  🏷️  review: {review_result[:100]}")

                if "review_retries" in node_output and node_output["review_retries"]:
                    logger.debug(f"  🔁 retries: {node_output['review_retries']}")

                if "messages" in node_output:
                    for msg in node_output["messages"]:
                        role = type(msg).__name__
                        if role == "AIMessage" and not getattr(msg, "tool_calls", None):
                            preview = msg.content[:120].replace("\n", " ")
                            logger.debug(f"  💬 {preview}...")
                            final_output = msg.content

        logger.info(f"✅ Agent 流水线完成，共 {step_count} 步")

        return {
            "final_output": final_output,
            "review_result": review_result,
            "step_count": step_count,
        }

    finally:
        reset_workspace(_ws_token)


# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

def main() -> int:
    """
    AutoPatch 主流程。

    Returns:
        退出码（0 = 成功，1 = 失败）
    """
    setup_logging()

    from config import validate_required_env
    try:
        validate_required_env()
    except EnvironmentError as e:
        logger.error(str(e))
        return 1

    parser = build_arg_parser()
    args = parser.parse_args()

    # ── 打印 Banner ──
    logger.info("🤖 AutoPatch — GitHub Issue Auto-Fix Agent")
    logger.info(f"  仓库  : {args.repo_url}")
    logger.info(f"  Issue : #{args.issue_number}")
    logger.info(f"  输出  : {args.output_dir}")

    start_time = datetime.now()

    # ── Step 1: 解析仓库 URL ──
    logger.info("🔍 [1/5] 解析仓库 URL...")
    try:
        repo_info = parse_github_url(args.repo_url)
        logger.info(f"  ✅ 解析成功: {repo_info.full_name}")
    except ValueError as e:
        logger.error(f"  ❌ URL 解析失败: {e}")
        return 1

    # ── Step 2: 拉取 Issue 内容 ──
    logger.info(f"📥 [2/5] 拉取 Issue #{args.issue_number}...")
    client = GitHubClient()
    try:
        issue = client.fetch_issue(repo_info, args.issue_number)
        issue_text = issue.to_prompt_text()
        logger.info(f"  ✅ Issue 标题: {issue.title}")
        logger.info(f"  标签: {issue.labels or '无'} | 评论数: {len(issue.comments)}")
    except Exception as e:
        logger.error(f"  ❌ 拉取 Issue 失败: {type(e).__name__}: {e}")
        logger.error("  提示: 请检查 GITHUB_TOKEN 是否已设置，以及 Issue 编号是否正确")
        return 1

    # 拉取仓库元数据（获取主要编程语言，失败不阻断流程）
    try:
        meta = client.fetch_repo_metadata(repo_info)
        repo_language = meta.get("language") or "Unknown"
        logger.info(f"  🔤 仓库语言: {repo_language}")
    except Exception:
        repo_language = "Unknown"

    # ── Step 3: Clone 仓库 ──
    logger.info("📦 [3/5] 准备工作区...")

    # 确定工作区目录和是否需要 clone
    if args.workspace_dir:
        workspace_path = Path(args.workspace_dir).resolve()
        if not workspace_path.exists():
            logger.error(f"  ❌ 指定的工作区目录不存在: {workspace_path}")
            return 1
        logger.info(f"  ✅ 使用已有工作区: {workspace_path}")
        workspace = None  # 不需要 clone，也不需要清理
    else:
        # 创建临时目录并 clone
        tmp_base = tempfile.mkdtemp(prefix=f"autopatch_{repo_info.repo}_")
        workspace_path = Path(tmp_base)
        workspace = RepoWorkspace(
            repo_info=repo_info,
            target_dir=str(workspace_path),
            branch=args.branch,
        )
        try:
            workspace.clone()
        except RuntimeError as e:
            logger.error(f"  ❌ Clone 失败: {e}")
            workspace.cleanup()
            return 1

    try:
        # ── Step 4: 运行 Agent ──
        logger.info("🤖 [4/5] 运行 Agent 流水线...")
        logger.info(f"  工作区: {workspace_path}")

        agent_result = run_agent_on_issue(
            issue_text=issue_text,
            working_dir=str(workspace_path),
            repo_language=repo_language,
        )

        # ── Step 5: 生成 Diff 文件 ──
        logger.info("📄 [5/5] 生成 Diff 文件...")

        # 检查变更文件
        changed = get_changed_files(str(workspace_path))
        if not changed:
            logger.warning("  ⚠️  Agent 未对仓库文件做任何修改，跳过 diff 生成")
            _print_final_report(args, issue, agent_result, diff_path=None, elapsed=datetime.now() - start_time)
            return 0

        logger.info(f"  检测到 {len(changed)} 个变更文件:")
        for c in changed:
            logger.info(f"    [{c['status']:10s}] {c['path']}")

        # 生成 diff 内容
        try:
            diff_content = generate_diff(str(workspace_path))
        except RuntimeError as e:
            logger.error(f"  ❌ diff 生成失败: {e}")
            return 1

        # 写入 .diff 文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        diff_filename = f"issue-{args.issue_number}_{timestamp}.diff"
        diff_path = Path(args.output_dir) / diff_filename

        diff_path = write_diff_file(
            diff_content=diff_content,
            output_path=diff_path,
            repo_url=repo_info.clone_url,
            issue_number=args.issue_number,
            review_result=agent_result.get("review_result", ""),
        )

        # 打印 diff 摘要
        print_diff_summary(diff_content)

        # ── 最终报告 ──
        elapsed = datetime.now() - start_time
        _print_final_report(args, issue, agent_result, diff_path=diff_path, elapsed=elapsed)

    finally:
        # 清理临时工作区（除非用户要求保留）
        if workspace and not args.keep_workspace:
            workspace.cleanup()
        elif workspace and args.keep_workspace:
            logger.info(f"📁 工作区已保留（--keep-workspace）: {workspace_path}")

    return 0


def _print_final_report(
    args: argparse.Namespace,
    issue,
    agent_result: dict,
    diff_path: Optional[Path],
    elapsed,
) -> None:
    """打印最终的完整摘要报告。"""
    logger.info("🎉 AutoPatch 运行完毕")
    logger.info(f"  仓库       : {args.repo_url}")
    logger.info(f"  Issue      : #{args.issue_number} — {issue.title}")
    logger.info(f"  总步骤数   : {agent_result.get('step_count', '?')}")
    logger.info(f"  总耗时     : {elapsed.total_seconds():.1f} 秒")

    review = agent_result.get("review_result", "")
    if review.upper().startswith("PASS"):
        logger.info(f"  评审结论   : ✅ PASS")
    elif review.upper().startswith("REJECT"):
        logger.warning(f"  评审结论   : ⚠️  {review[:80]}")
    else:
        logger.info(f"  评审结论   : {review[:80] or '未知'}")

    if diff_path:
        logger.info(f"  Diff 文件  : {diff_path.resolve()}")
        logger.info(f"  应用补丁命令（在目标仓库根目录执行）:")
        logger.info(f"  git apply {diff_path.resolve()}")
    else:
        logger.info(f"  Diff 文件  : 无（未检测到文件变更）")

    if agent_result.get("final_output"):
        logger.info(f"  Agent 最终报告:")
        for line in agent_result["final_output"].splitlines():
            logger.info(f"  {line}")


# ══════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.warning("⏹️  用户中断")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 未捕获的异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
