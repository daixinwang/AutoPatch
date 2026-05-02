"""
server.py
---------
AutoPatch FastAPI 后端服务。

提供 SSE（Server-Sent Events）端点，将 LangGraph Agent 流水线的每一步
进展实时推送给前端，并支持断点续传（中断后从最后完成的节点恢复）。

端点：
  POST /api/patch          启动一次完整的 AutoPatch 流水线（SSE 流）
  POST /api/patch/resume   恢复被中断的任务（SSE 流）
  GET  /api/tasks          列出所有历史任务及其状态
  DELETE /api/tasks/{id}   删除任务记录（并可选清理 workspace）
  GET  /api/health         健康检查

SSE 事件格式（每条 JSON）：
  { "type": "task",   "taskId": "uuid", "status": "new|resumed" }

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
  DATABASE_URL=postgresql://... uvicorn server:app --reload --port 8000
"""

import asyncio
import contextvars
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import logging

from logging_config import setup_logging

from github_client import GitHubClient, RepoWorkspace, parse_github_url
from diff_generator import generate_diff, get_changed_files, write_diff_file
from agent.graph import build_graph, AgentState
from langchain_core.messages import HumanMessage
from tools.workspace import set_workspace, reset_workspace
from task_store import TaskStore
from config import MAX_CONCURRENT_PATCHES as _CFG_MAX_CONCURRENT, DB_POOL_MAX_SIZE, RECURSION_LIMIT

setup_logging()
logger = logging.getLogger(__name__)

# ── FastAPI 应用初始化 ────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """FastAPI lifespan：启动时初始化 Checkpointer 和任务存储；关闭时释放连接池。"""
    global agent_app, task_store, _db_pool

    task_store = TaskStore()
    _db_pool = None

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.warning("DATABASE_URL 未设置，断点续传不可用，使用内存模式运行")
        agent_app = build_graph(checkpointer=None)
    else:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            _db_pool = ConnectionPool(
                conninfo=db_url,
                max_size=DB_POOL_MAX_SIZE,
                kwargs={"autocommit": True, "prepare_threshold": 0},
                open=True,
            )
            checkpointer = PostgresSaver(_db_pool)
            checkpointer.setup()   # 幂等：建表（已存在则跳过）
            agent_app = build_graph(checkpointer=checkpointer)
            logger.info("PostgreSQL Checkpointer 初始化完成，断点续传已启用")
        except Exception:
            logger.warning("Checkpointer 初始化失败，降级为内存模式", exc_info=True)
            agent_app = build_graph(checkpointer=None)
            if _db_pool is not None:
                # 部分初始化失败时也关闭，避免连接泄漏
                try:
                    _db_pool.close()
                except Exception:
                    logger.debug("关闭半初始化连接池时出错", exc_info=True)
                _db_pool = None

    try:
        yield   # 应用运行期间
    finally:
        # 关闭 PostgreSQL 连接池，防止长跑时连接泄漏
        if _db_pool is not None:
            try:
                _db_pool.close()
                logger.info("PostgreSQL 连接池已关闭")
            except Exception:
                logger.warning("关闭连接池失败", exc_info=True)
            _db_pool = None


fastapi_app = FastAPI(
    title="AutoPatch API",
    description="LangGraph multi-agent GitHub Issue auto-fix service",
    version="1.0.0",
    lifespan=_lifespan,
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
_MAX_CONCURRENT = _CFG_MAX_CONCURRENT
_pipeline_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

# ── API 认证 ──────────────────────────────────────────────
# 设置 AUTOPATCH_API_KEY 环境变量启用 Bearer token 认证。
# 未设置时允许所有请求（开发模式），启动时打印警告。
_API_KEY = os.getenv("AUTOPATCH_API_KEY", "")
if not _API_KEY:
    logger.warning("AUTOPATCH_API_KEY 未设置，API 端点无认证保护（仅限开发环境）")


async def _verify_api_key(request: Request) -> None:
    """FastAPI 依赖：校验 Authorization: Bearer <key>。"""
    if not _API_KEY:
        return  # 未配置 API Key，跳过认证（开发模式）
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _API_KEY:
        raise HTTPException(status_code=401, detail="未授权：无效的 API Key")

# ── 全局有状态对象（在 startup 中初始化）────────────────────
# agent_app: 带 PostgresSaver checkpointer 的 LangGraph 实例
# task_store: 任务元数据持久化（tasks/*.json）
# _db_pool:  PostgreSQL 连接池（lifespan 退出时关闭）
agent_app = None
task_store: Optional[TaskStore] = None
_db_pool = None

# 防止同一 task_id 并发恢复：锁字典 + 字典访问的元锁
_resume_locks: dict[str, asyncio.Lock] = {}
_resume_locks_meta_lock = asyncio.Lock()


async def _acquire_resume_lock(task_id: str) -> asyncio.Lock:
    """获取（或创建）指定 task_id 的恢复锁。"""
    async with _resume_locks_meta_lock:
        lock = _resume_locks.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            _resume_locks[task_id] = lock
        return lock


async def _release_resume_lock(task_id: str) -> None:
    """释放并清理指定 task_id 的锁条目（避免字典无限增长）。"""
    async with _resume_locks_meta_lock:
        lock = _resume_locks.get(task_id)
        # 仅当锁未被其他协程持有时才删除
        if lock is not None and not lock.locked():
            _resume_locks.pop(task_id, None)



# ── 请求体定义 ────────────────────────────────────────────
class PatchRequest(BaseModel):
    repoUrl:     str   # e.g. "owner/repo" or full https URL
    issueNumber: int   # e.g. 42


class ResumeRequest(BaseModel):
    taskId: str        # 中断任务的 UUID（由 /api/patch 的 task 事件提供）


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


def task_event(task_id: str, status: str) -> str:
    return sse_event({"type": "task", "taskId": task_id, "status": status})


def result_event(diff: str, review_result: str, step_count: int, changed_files: list) -> str:
    return sse_event({
        "type":          "result",
        "diff":          diff,
        "reviewResult":  review_result,
        "stepCount":     step_count,
        "changedFiles":  changed_files,
    })


# ── 核心流水线（异步生成器）────────────────────────────────

def _make_task_config(task_id: str) -> dict:
    """构造带 thread_id 的 LangGraph 运行配置（用于 checkpoint 索引）。"""
    return {"recursion_limit": RECURSION_LIMIT, "configurable": {"thread_id": task_id}}


def _start_agent_stream(
    input_state,
    task_config: dict,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """在后台线程中运行 LangGraph stream，把每个 chunk 放入队列。

    input_state=None 时从 checkpoint 恢复。
    必须在 copy_context().run() 中调用以继承 workspace ContextVar。
    """
    import threading

    def _run():
        try:
            for chunk in agent_app.stream(
                input_state,
                config=task_config,
                stream_mode=["updates", "messages"],
            ):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
            loop.call_soon_threadsafe(queue.put_nowait, None)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)

    ctx = contextvars.copy_context()
    thread = threading.Thread(target=ctx.run, args=(_run,), daemon=True)
    thread.start()


async def _consume_agent_stream(
    queue: asyncio.Queue,
    active_nodes: set[str],
) -> AsyncGenerator[tuple[str, int, str], None]:
    """消费 LangGraph stream 队列，生成 SSE 事件。

    Yields:
        (sse_str, step_count_delta, review_result_update) 三元组。
        step_count_delta 仅在 updates 模式时为 1，其余为 0。
        review_result_update 非空时为最新评审结果。
    """
    while True:
        chunk = await queue.get()

        if chunk is None:
            break

        if isinstance(chunk, Exception):
            yield log_event(f"Agent 运行异常: {chunk}", "error"), 0, ""
            yield sse_event({"type": "error", "message": str(chunk)}), 0, ""
            return

        mode, data = chunk

        # ── messages 模式：token 级流式块 ────────────────
        if mode == "messages":
            msg_chunk, metadata = data
            node_name = metadata.get("langgraph_node", "")
            node_id = NODE_ID_MAP.get(node_name, node_name)
            content = getattr(msg_chunk, "content", "")
            if content and isinstance(content, str):
                yield token_event(node_id, content), 0, ""
            await asyncio.sleep(0)
            continue

        # ── updates 模式：节点级状态更新 ─────────────────
        review_update = ""

        for node_name, node_output in data.items():
            node_id = NODE_ID_MAP.get(node_name, node_name)

            if node_id not in active_nodes and node_name != "tool_node":
                active_nodes.add(node_id)
                yield node_event(node_id, "running"), 0, ""

            display = node_name.replace("_node", "").replace("_", " ").title()

            if "plan" in node_output and node_output["plan"]:
                preview = node_output["plan"][:200].replace("\n", " ")
                yield log_event(f"执行计划已生成: {preview}...", "success", "Planner"), 0, ""
                yield node_event("planner", "done"), 0, ""

            if "test_output" in node_output and node_output["test_output"]:
                key_lines = [
                    l for l in node_output["test_output"].splitlines()
                    if any(kw in l.upper() for kw in ["PASS", "FAIL", "ERROR", "EXIT", "OK"])
                ]
                summary = " | ".join(key_lines[:3]) if key_lines else node_output["test_output"][:120]
                yield log_event(f"测试结果: {summary}", "success", "TestRunner"), 0, ""
                yield node_event("testrunner", "done"), 0, ""

            if "review_result" in node_output and node_output["review_result"]:
                review_update = node_output["review_result"]
                is_pass = review_update.upper().startswith("PASS")
                level = "success" if is_pass else "warn"
                yield log_event(f"评审结论: {review_update[:120]}", level, "Reviewer"), 0, ""
                retries = node_output.get("review_retries", 0)
                if is_pass:
                    yield node_event("reviewer", "done"), 0, ""
                elif retries and retries > 0:
                    yield node_event("coder", "retrying", f"第 {retries} 次打回"), 0, ""
                    yield node_event("reviewer", "retrying", f"第 {retries} 次打回"), 0, ""

            if "messages" in node_output:
                for msg in node_output["messages"]:
                    msg_type = type(msg).__name__
                    if msg_type == "AIMessage" and hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            args_preview = ", ".join(
                                f"{k}={str(v)[:40]!r}" for k, v in (tc.get("args") or {}).items()
                            )
                            yield log_event(
                                f"调用工具: {tc['name']}({args_preview})",
                                "tool",
                                display,
                            ), 0, ""
                    elif msg_type == "AIMessage" and not getattr(msg, "tool_calls", None):
                        if msg.content and len(msg.content) > 0:
                            preview = str(msg.content)[:150].replace("\n", " ")
                            yield log_event(preview, "info", display), 0, ""
                            if node_id not in ("coder",):
                                yield node_event(node_id, "done"), 0, ""

        yield "", 1, review_update  # step_count += 1 信号
        await asyncio.sleep(0)


async def _generate_and_save_diff(
    tmp_dir: str,
    issue_number: int,
    repo_url: str,
    review_result: str,
) -> tuple[str, list[str]]:
    """生成 diff 并保存到 patches/ 目录，返回 (diff_content, changed_files)。"""
    loop = asyncio.get_running_loop()

    try:
        diff_content = await loop.run_in_executor(None, generate_diff, tmp_dir)
    except RuntimeError as e:
        diff_content = ""
        logger.warning("Diff 生成失败: %s", e)

    changed_files_raw = await loop.run_in_executor(None, get_changed_files, tmp_dir)
    changed_files = [c["path"] for c in changed_files_raw]

    if diff_content.strip():
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        diff_path = Path("patches") / f"issue-{issue_number}_{ts}.diff"
        await loop.run_in_executor(
            None, write_diff_file, diff_content, diff_path,
            repo_url, issue_number, review_result,
        )
        logger.info("Diff 已保存: %s", diff_path)

    return diff_content, changed_files


async def run_pipeline(req: PatchRequest) -> AsyncGenerator[str, None]:
    """
    完整的 AutoPatch 流水线，以 SSE 事件流的形式逐步推送进度。

    步骤：
      1. 解析仓库 URL
      2. 拉取 GitHub Issue
      3. Clone 仓库（保存任务元数据）
      4. 运行 LangGraph Agent（在线程池中同步执行，带 checkpoint）
      5. 生成 diff 并返回结果

    中断时（客户端断连 / 服务崩溃）workspace 目录保留，任务状态标记为
    interrupted，可通过 POST /api/patch/resume 恢复。
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
    task_id = str(uuid.uuid4())
    task_record_created = False
    completed = False

    try:
        # 最先发出 task 事件，让前端尽早拿到 task_id
        yield task_event(task_id, "new")

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

        # Clone 成功后保存任务元数据（此后中断均可续传）
        issue_text = issue.to_prompt_text()
        if task_store is not None:
            task_store.create(
                repo_url=req.repoUrl,
                issue_number=req.issueNumber,
                workspace_path=tmp_dir,
                repo_language=repo_language,
                issue_text=issue_text,
                task_id=task_id,
            )
        task_record_created = True
        await asyncio.sleep(0)

        # ── Step 4: 运行 LangGraph Agent ────────────────
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

        task_config = _make_task_config(task_id)
        step_count = 0
        review_result = ""
        active_nodes: set[str] = set()

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        _start_agent_stream(initial_state, task_config, queue, loop)

        async for sse_str, delta, rev_update in _consume_agent_stream(queue, active_nodes):
            step_count += delta
            if rev_update:
                review_result = rev_update
            if sse_str:
                yield sse_str

        yield node_event("coder", "done")

        # ── Step 5: 生成 Diff ────────────────────────────
        yield log_event("正在生成 diff 补丁...", "info")
        diff_content, changed_files = await _generate_and_save_diff(
            tmp_dir, req.issueNumber, repo_info.clone_url, review_result,
        )
        if diff_content.strip():
            yield log_event(f"✅ Diff 已保存", "success")

        elapsed_ms = int(time.time() * 1000) - start_ms
        yield log_event(f"🎉 流水线完成！耗时 {elapsed_ms / 1000:.1f}s", "system")

        yield result_event(
            diff=diff_content,
            review_result=review_result,
            step_count=step_count,
            changed_files=changed_files,
        )
        completed = True

    except Exception as e:
        logger.error("流水线异常", exc_info=True)
        yield log_event(f"流水线异常: {type(e).__name__}: {e}", "error")
        yield sse_event({"type": "error", "message": str(e)})

    finally:
        _pipeline_semaphore.release()
        if _ws_token is not None:
            reset_workspace(_ws_token)
        if task_store is not None and task_record_created:
            if completed:
                task_store.update_status(task_id, "completed")
                if workspace:
                    workspace.cleanup()   # 成功完成后才清理 workspace
            else:
                task_store.update_status(task_id, "interrupted")
                # workspace 保留，供续传时复用
        elif workspace:
            workspace.cleanup()           # 任务记录未创建（前期失败），直接清理
        yield sse_event({"type": "done"})


async def resume_pipeline(task_id: str) -> AsyncGenerator[str, None]:
    """
    从最后一个 checkpoint 恢复被中断的 AutoPatch 流水线。

    前提条件：
      - task_id 对应的任务存在且状态为 interrupted
      - workspace 目录未被删除
      - PostgreSQL checkpointer 已正确配置（DATABASE_URL）

    并发保护：同一 task_id 不允许多客户端同时恢复，第二个请求会立即拒绝，
    防止两个 worker 从同一 checkpoint 恢复后互相覆盖状态、重复清理 workspace。
    """
    # 同一 task_id 的并发恢复保护：如果锁已被持有，立即拒绝（不阻塞排队）
    resume_lock = await _acquire_resume_lock(task_id)
    if resume_lock.locked():
        yield sse_event({
            "type": "error",
            "message": f"任务 {task_id} 正在被其他会话恢复，请稍后再试",
        })
        yield sse_event({"type": "done"})
        return

    await resume_lock.acquire()
    try:
        async for chunk in _resume_pipeline_inner(task_id):
            yield chunk
    finally:
        resume_lock.release()
        await _release_resume_lock(task_id)


async def _resume_pipeline_inner(task_id: str) -> AsyncGenerator[str, None]:
    """resume_pipeline 主体（在 task_id 锁保护下执行；自行管理并发信号量）。"""
    # 超出并发上限时立即拒绝
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
    _ws_token = None
    completed = False
    tmp_dir = ""    # 成功加载 record 后赋值，finally 中用于清理

    try:
        # ── 加载任务记录 ──────────────────────────────────
        if task_store is None:
            yield sse_event({"type": "error", "message": "任务存储未初始化"})
            return

        record = task_store.get(task_id)
        if record is None:
            yield sse_event({"type": "error", "message": f"任务 {task_id} 不存在"})
            return

        if record.status not in ("interrupted", "running"):
            yield sse_event({
                "type": "error",
                "message": f"任务 {task_id} 状态为 {record.status}，无法续传（仅 interrupted 状态可续传）",
            })
            return

        tmp_dir = record.workspace_path
        if not Path(tmp_dir).exists():
            yield sse_event({
                "type": "error",
                "message": f"工作目录 {tmp_dir} 不存在，无法续传（请重新发起新任务）",
            })
            return

        if agent_app is None:
            yield sse_event({"type": "error", "message": "Agent 未初始化"})
            return

        # 检查 checkpointer 是否可用（无 checkpointer 则无法续传）
        if not hasattr(agent_app, "checkpointer") or agent_app.checkpointer is None:
            yield sse_event({
                "type": "error",
                "message": "断点续传需要配置 DATABASE_URL，当前以内存模式运行",
            })
            return

        task_store.update_status(task_id, "running")
        yield task_event(task_id, "resumed")
        yield log_event(f"正在从断点恢复任务 {task_id}...", "system")
        yield log_event(f"工作目录: {tmp_dir}", "info")

        # 设置工作目录上下文
        _ws_token = set_workspace(tmp_dir)

        task_config = _make_task_config(task_id)
        step_count = 0
        review_result = ""
        active_nodes: set[str] = set()

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        _start_agent_stream(None, task_config, queue, loop)  # None = 从 checkpoint 恢复

        async for sse_str, delta, rev_update in _consume_agent_stream(queue, active_nodes):
            step_count += delta
            if rev_update:
                review_result = rev_update
            if sse_str:
                yield sse_str

        yield node_event("coder", "done")

        # ── 生成 Diff ─────────────────────────────────────
        yield log_event("正在生成 diff 补丁...", "info")
        diff_content, changed_files = await _generate_and_save_diff(
            tmp_dir, record.issue_number,
            f"https://github.com/{record.repo_url}.git", review_result,
        )
        if diff_content.strip():
            yield log_event(f"✅ Diff 已保存", "success")

        elapsed_ms = int(time.time() * 1000) - start_ms
        yield log_event(f"🎉 续传流水线完成！耗时 {elapsed_ms / 1000:.1f}s", "system")

        yield result_event(
            diff=diff_content,
            review_result=review_result,
            step_count=step_count,
            changed_files=changed_files,
        )
        completed = True

    except Exception as e:
        logger.error("续传流水线异常", exc_info=True)
        yield log_event(f"续传流水线异常: {type(e).__name__}: {e}", "error")
        yield sse_event({"type": "error", "message": str(e)})

    finally:
        _pipeline_semaphore.release()
        if _ws_token is not None:
            reset_workspace(_ws_token)
        if task_store is not None:
            if completed:
                task_store.update_status(task_id, "completed")
                if tmp_dir and Path(tmp_dir).exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                task_store.update_status(task_id, "interrupted")
        yield sse_event({"type": "done"})


# ── API 路由 ──────────────────────────────────────────────

@fastapi_app.get("/api/health")
async def health():
    """健康检查。"""
    return {"status": "ok", "service": "AutoPatch"}


_SSE_HEADERS = {
    "Cache-Control":     "no-cache",
    "X-Accel-Buffering": "no",   # 禁用 Nginx 缓冲，确保实时推送
}


@fastapi_app.post("/api/patch", dependencies=[Depends(_verify_api_key)])
async def patch_endpoint(req: PatchRequest):
    """
    启动 AutoPatch 流水线，以 SSE 流式推送进度和结果。

    第一条 SSE 事件为 {"type": "task", "taskId": "<uuid>", "status": "new"}，
    客户端应保存 taskId 供后续续传使用。
    """
    return StreamingResponse(
        run_pipeline(req),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@fastapi_app.post("/api/patch/resume", dependencies=[Depends(_verify_api_key)])
async def resume_endpoint(req: ResumeRequest):
    """
    恢复被中断的 AutoPatch 任务，从最后完成的节点继续执行。

    需要在 .env 中配置 DATABASE_URL（PostgreSQL），否则返回错误。
    """
    return StreamingResponse(
        resume_pipeline(req.taskId),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@fastapi_app.get("/api/tasks")
async def list_tasks_endpoint():
    """列出所有历史任务及其状态（按创建时间降序）。"""
    if task_store is None:
        return {"tasks": []}
    return {"tasks": [r.to_dict() for r in task_store.list_all()]}


@fastapi_app.delete("/api/tasks/{task_id}", dependencies=[Depends(_verify_api_key)])
async def delete_task_endpoint(task_id: str):
    """
    删除任务记录，同时删除对应的 workspace 目录（释放磁盘空间）。

    注意：正在运行中（status=running）的任务也可删除，但不会中断其线程。
    """
    if task_store is None:
        raise HTTPException(status_code=503, detail="任务存储未初始化")
    deleted = task_store.delete(task_id, remove_workspace=True)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return {"deleted": task_id}


# ── 入口 ──────────────────────────────────────────────────
app = fastapi_app   # uvicorn server:app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
