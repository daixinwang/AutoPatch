"""
server.py
---------
AutoPatch FastAPI 后端服务。

提供一个 SSE（Server-Sent Events）端点，将 LangGraph Agent 流水线的
每一步进展实时推送给前端，包括：
  - 节点状态变更（running / done / error）
  - 终端日志（info / tool / success / error）
  - 最终 diff 内容和评审结论

端点：
  POST /api/patch          启动一次完整的 AutoPatch 流水线（SSE 流）
  GET  /api/health         健康检查

SSE 事件格式（每条 JSON）：
  { "type": "log",    "level": "info|tool|success|error|system|warn",
    "node": "Planner", "message": "..." }

  { "type": "node",   "node": "planner|coder|testrunner|reviewer",
    "status": "running|done|error|retrying", "detail": "..." }

  { "type": "result", "diff": "...", "reviewResult": "...",
    "stepCount": 12,  "changedFiles": ["calc.py"] }

  { "type": "error",  "message": "..." }

  { "type": "done" }

运行方式：
  source .venv/bin/activate
  uvicorn server:app --reload --port 8000
"""

import asyncio
import contextvars
import json
import os
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from github_client import GitHubClient, RepoWorkspace, parse_github_url
from diff_generator import generate_diff, get_changed_files, write_diff_file
from agent.graph import app as agent_app, AgentState, APP_CONFIG
from langchain_core.messages import HumanMessage
from tools.workspace import set_workspace, reset_workspace

# ── FastAPI 应用初始化 ────────────────────────────────────
fastapi_app = FastAPI(
    title="AutoPatch API",
    description="LangGraph multi-agent GitHub Issue auto-fix service",
    version="1.0.0",
)

# CORS：从环境变量读取，逗号分隔；未配置时退回到本地开发默认值
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限制同时进行的 AutoPatch 流水线数量，防止资源耗尽
# 通过环境变量 MAX_CONCURRENT_PATCHES 配置（默认 3）
_MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_PATCHES", "3"))
_pipeline_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

# ── 请求体定义 ────────────────────────────────────────────
class PatchRequest(BaseModel):
    repoUrl:     str   # e.g. "owner/repo" or full https URL
    issueNumber: int   # e.g. 42


# ── 节点名 → 前端 ID 映射 ─────────────────────────────────
NODE_ID_MAP = {
    "planner_node":     "planner",
    "coder_node":       "coder",
    "tool_node":        "coder",       # tool_node 属于 Coder 阶段
    "test_runner_node": "testrunner",
    "reviewer_node":    "reviewer",
}

# ── SSE 事件构造工具 ──────────────────────────────────────

def sse_event(data: dict) -> str:
    """将字典序列化为 SSE data 行格式。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def log_event(message: str, level: str = "info", node: Optional[str] = None) -> str:
    return sse_event({"type": "log", "level": level, "node": node, "message": message})


def node_event(node_id: str, status: str, detail: str = "") -> str:
    return sse_event({"type": "node", "node": node_id, "status": status, "detail": detail})


def token_event(node_id: str, content: str) -> str:
    return sse_event({"type": "token", "node": node_id, "content": content})


def result_event(diff: str, review_result: str, step_count: int, changed_files: list) -> str:
    return sse_event({
        "type":          "result",
        "diff":          diff,
        "reviewResult":  review_result,
        "stepCount":     step_count,
        "changedFiles":  changed_files,
    })


# ── 核心流水线（异步生成器）────────────────────────────────

async def run_pipeline(req: PatchRequest) -> AsyncGenerator[str, None]:
    """
    完整的 AutoPatch 流水线，以 SSE 事件流的形式逐步推送进度。

    步骤：
      1. 解析仓库 URL
      2. 拉取 GitHub Issue
      3. Clone 仓库
      4. 运行 LangGraph Agent（在线程池中同步执行）
      5. 生成 diff 并返回结果
    """
    # 超出并发上限时立即拒绝，避免无限排队
    try:
        await asyncio.wait_for(_pipeline_semaphore.acquire(), timeout=0)
    except asyncio.TimeoutError:
        yield sse_event({
            "type": "error",
            "message": f"服务器繁忙，最多支持 {_MAX_CONCURRENT} 个并发任务，请稍后重试",
        })
        yield sse_event({"type": "done"})
        return

    start_ms = int(time.time() * 1000)
    workspace = None
    _ws_token = None

    try:
        # ── Step 1: 解析 URL ──────────────────────────────
        yield log_event("解析仓库 URL...", "system")
        try:
            repo_info = parse_github_url(req.repoUrl)
        except ValueError as e:
            yield log_event(f"URL 解析失败: {e}", "error")
            yield sse_event({"type": "error", "message": str(e)})
            return
        yield log_event(f"✅ 仓库: {repo_info.full_name}", "success")
        await asyncio.sleep(0)

        # ── Step 2: 拉取 Issue ───────────────────────────
        yield log_event(f"正在从 GitHub 拉取 Issue #{req.issueNumber}...", "info")
        client = GitHubClient()
        try:
            issue = await asyncio.get_running_loop().run_in_executor(
                None, client.fetch_issue, repo_info, req.issueNumber
            )
        except Exception as e:
            yield log_event(f"拉取 Issue 失败: {e}", "error")
            yield sse_event({"type": "error", "message": f"拉取 Issue 失败: {e}"})
            return
        yield log_event(f"✅ Issue 拉取成功: {issue.title}", "success")
        yield log_event(f"标签: {issue.labels or '无'} | 评论数: {len(issue.comments)}", "info")

        # 拉取仓库元数据，获取主要编程语言
        try:
            meta = await asyncio.get_running_loop().run_in_executor(
                None, client.fetch_repo_metadata, repo_info
            )
            repo_language = meta.get("language") or "Unknown"
        except Exception:
            repo_language = "Unknown"
        yield log_event(f"仓库语言: {repo_language}", "info")
        await asyncio.sleep(0)

        # ── Step 3: Clone 仓库 ───────────────────────────
        tmp_dir = tempfile.mkdtemp(prefix=f"autopatch_{repo_info.repo}_")
        workspace = RepoWorkspace(repo_info=repo_info, target_dir=tmp_dir)
        yield log_event(f"正在 clone 仓库 {repo_info.clone_url}...", "info")
        try:
            await asyncio.get_running_loop().run_in_executor(None, workspace.clone)
        except RuntimeError as e:
            yield log_event(f"Clone 失败: {e}", "error")
            yield sse_event({"type": "error", "message": str(e)})
            return
        yield log_event(f"✅ Clone 完成 → {tmp_dir}", "success")
        await asyncio.sleep(0)

        # ── Step 4: 运行 LangGraph Agent ────────────────
        issue_text = issue.to_prompt_text()
        initial_state: AgentState = {
            "messages":       [HumanMessage(content=f"Issue 需求：\n\n{issue_text}")],
            "issue_task":     issue_text,
            "repo_language":  repo_language,
            "plan":           "",
            "test_output":    "",
            "review_result":  "",
            "review_retries": 0,
        }

        # 设置当前请求上下文的工作目录（不修改全局 CWD，线程安全）
        _ws_token = set_workspace(tmp_dir)
        yield log_event(f"工作目录已设置: {tmp_dir}", "system")

        step_count = 0
        review_result = ""
        active_nodes: set[str] = set()

        # LangGraph stream 是同步的，用 run_in_executor 跑在线程中
        # 通过队列桥接同步迭代和异步 yield
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def stream_in_thread():
            """在线程中运行 LangGraph stream，把每个 chunk 放入队列。

            stream_mode=["updates", "messages"] 同时启用两种模式：
              - updates : 节点级状态更新（{node_name: node_output}）
              - messages: token 级流式块（(AIMessageChunk, metadata)）
            每个 chunk 为 (mode, data) 元组。
            """
            try:
                for chunk in agent_app.stream(
                    initial_state,
                    config=APP_CONFIG,
                    stream_mode=["updates", "messages"],
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
                loop.call_soon_threadsafe(queue.put_nowait, None)  # 结束信号
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)

        # 将当前 asyncio Task 的 ContextVar 快照传递给后台线程，
        # 确保工具读取到正确的 workspace_dir（而非其他并发请求的目录）
        import threading
        ctx = contextvars.copy_context()
        thread = threading.Thread(target=ctx.run, args=(stream_in_thread,), daemon=True)
        thread.start()

        # 从队列消费事件并 yield SSE
        while True:
            chunk = await queue.get()

            # 结束信号
            if chunk is None:
                break

            # 异常
            if isinstance(chunk, Exception):
                yield log_event(f"Agent 运行异常: {chunk}", "error")
                yield sse_event({"type": "error", "message": str(chunk)})
                return

            # chunk 为 (mode, data) 元组
            mode, data = chunk

            # ── messages 模式：token 级流式块 ────────────────
            if mode == "messages":
                msg_chunk, metadata = data
                node_name = metadata.get("langgraph_node", "")
                node_id = NODE_ID_MAP.get(node_name, node_name)
                content = getattr(msg_chunk, "content", "")
                # 只推送文本 token，跳过工具调用 chunk（content 为空）
                if content and isinstance(content, str):
                    yield token_event(node_id, content)
                await asyncio.sleep(0)
                continue

            # ── updates 模式：节点级状态更新 ─────────────────
            step_count += 1

            for node_name, node_output in data.items():
                node_id = NODE_ID_MAP.get(node_name, node_name)

                # 节点进入 running 状态（首次出现）
                if node_id not in active_nodes and node_name != "tool_node":
                    active_nodes.add(node_id)
                    yield node_event(node_id, "running")

                # ── 解析节点输出，生成日志事件 ──
                display = node_name.replace("_node", "").replace("_", " ").title()

                if "plan" in node_output and node_output["plan"]:
                    preview = node_output["plan"][:200].replace("\n", " ")
                    yield log_event(f"执行计划已生成: {preview}...", "success", "Planner")
                    yield node_event("planner", "done")

                if "test_output" in node_output and node_output["test_output"]:
                    # 提取关键行
                    key_lines = [
                        l for l in node_output["test_output"].splitlines()
                        if any(kw in l.upper() for kw in ["PASS", "FAIL", "ERROR", "EXIT", "OK"])
                    ]
                    summary = " | ".join(key_lines[:3]) if key_lines else node_output["test_output"][:120]
                    yield log_event(f"测试结果: {summary}", "success", "TestRunner")
                    yield node_event("testrunner", "done")

                if "review_result" in node_output and node_output["review_result"]:
                    review_result = node_output["review_result"]
                    is_pass = review_result.upper().startswith("PASS")
                    level = "success" if is_pass else "warn"
                    yield log_event(f"评审结论: {review_result[:120]}", level, "Reviewer")
                    retries = node_output.get("review_retries", 0)
                    if is_pass:
                        yield node_event("reviewer", "done")
                    elif retries and retries > 0:
                        yield node_event("coder", "retrying", f"第 {retries} 次打回")
                        yield node_event("reviewer", "retrying", f"第 {retries} 次打回")

                # 解析 messages 中的工具调用和 AI 消息
                if "messages" in node_output:
                    for msg in node_output["messages"]:
                        msg_type = type(msg).__name__
                        # 工具调用日志
                        if msg_type == "AIMessage" and hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                args_preview = ", ".join(
                                    f"{k}={str(v)[:40]!r}" for k, v in (tc.get("args") or {}).items()
                                )
                                yield log_event(
                                    f"调用工具: {tc['name']}({args_preview})",
                                    "tool",
                                    display,
                                )
                        # AI 完成消息（非工具调用）
                        elif msg_type == "AIMessage" and not getattr(msg, "tool_calls", None):
                            if msg.content and len(msg.content) > 0:
                                preview = str(msg.content)[:150].replace("\n", " ")
                                yield log_event(preview, "info", display)
                                # 标记节点完成
                                if node_id not in ("coder",):  # coder 在 test/review 后才算完成
                                    yield node_event(node_id, "done")

            await asyncio.sleep(0)  # 让出事件循环，保持响应性

        # 标记 coder 完成（若未被标记）
        if "coder" not in active_nodes or True:
            yield node_event("coder", "done")

        # ── Step 5: 生成 Diff ────────────────────────────
        yield log_event("正在生成 diff 补丁...", "info")

        try:
            diff_content = await asyncio.get_running_loop().run_in_executor(
                None, generate_diff, tmp_dir
            )
        except RuntimeError as e:
            diff_content = ""
            yield log_event(f"Diff 生成失败: {e}", "warn")

        changed_files_raw = await asyncio.get_running_loop().run_in_executor(
            None, get_changed_files, tmp_dir
        )
        changed_files = [c["path"] for c in changed_files_raw]

        # 写入 patches/ 目录
        if diff_content.strip():
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            diff_path = Path("patches") / f"issue-{req.issueNumber}_{ts}.diff"
            await asyncio.get_running_loop().run_in_executor(
                None,
                write_diff_file,
                diff_content,
                diff_path,
                repo_info.clone_url,
                req.issueNumber,
                review_result,
            )
            yield log_event(f"✅ Diff 已保存: {diff_path}", "success")

        elapsed_ms = int(time.time() * 1000) - start_ms
        yield log_event(f"🎉 流水线完成！耗时 {elapsed_ms / 1000:.1f}s", "system")

        # 推送最终结果
        yield result_event(
            diff=diff_content,
            review_result=review_result,
            step_count=step_count,
            changed_files=changed_files,
        )

    except Exception as e:
        yield log_event(f"流水线异常: {type(e).__name__}: {e}", "error")
        yield sse_event({"type": "error", "message": str(e)})

    finally:
        _pipeline_semaphore.release()
        if _ws_token is not None:
            reset_workspace(_ws_token)
        if workspace:
            workspace.cleanup()
        yield sse_event({"type": "done"})


# ── API 路由 ──────────────────────────────────────────────

@fastapi_app.get("/api/health")
async def health():
    """健康检查。"""
    return {"status": "ok", "service": "AutoPatch"}


@fastapi_app.post("/api/patch")
async def patch_endpoint(req: PatchRequest):
    """
    启动 AutoPatch 流水线，以 SSE 流式推送进度和结果。

    客户端使用 EventSource 或 fetch + ReadableStream 监听此端点。
    """
    return StreamingResponse(
        run_pipeline(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",   # 禁用 Nginx 缓冲，确保实时推送
        },
    )


# ── 入口 ──────────────────────────────────────────────────
app = fastapi_app   # uvicorn server:app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
