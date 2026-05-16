"""
agent/graph.py
--------------
LangGraph 多 Agent 协作架构（四阶段流水线）。

流程：
    START → planner_node → coder_node ⇄ tool_node
                ↑                          ↓
                │                   test_runner_node   ← 运行 pytest / 脚本
                │                          ↓
                └────── (REJECT) ── reviewer_node ──── PASS ──► END
                              (最多 MAX_REVIEW_RETRIES 次打回)

节点职责：
  - planner_node      : 拆解 Issue，输出结构化执行计划，写入 plan 字段
  - coder_node        : 按计划调用工具写代码（ReAct 循环）
  - tool_node         : 执行文件读写 + 代码检索工具（LangGraph 内置 ToolNode）
  - test_runner_node  : 自动运行 pytest / python 脚本，将结果写入 test_output
  - reviewer_node     : 结合 test_output + 静态检查做代码 Review，决策 PASS / REJECT

状态字段（AgentState）：
  - messages      : 消息历史（add_messages reducer 自动追加）
  - issue_task    : 原始 Issue 描述（只写一次）
  - plan          : Planner 输出的任务计划（纯文本）
  - test_output   : TestRunner 最新一次的执行报告（pytest 或 python 脚本输出）
  - review_result : Reviewer 最新评审结论（"PASS" | "REJECT: <原因>"）
  - review_retries: 当前已打回次数（防止无限循环）
"""

import os
from typing import Annotated, Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState, add_messages
from langgraph.prebuilt import ToolNode

# 导入所有本地工具
from tools.file_tools import edit_file, read_file, write_and_replace_file
from tools.search_tools import (
    find_definition,
    grep_in_file,
    list_directory,
    search_codebase,
)
from tools.execute_tools import run_pytest, run_python_script, run_test_command, verify_importable
from core.config import (
    MAX_CODER_STEPS,
    MAX_MESSAGE_CHARS,
    MAX_REVIEW_RETRIES,
    MAX_REVIEWER_TOOL_CALLS,
    PLANNER_MODEL_NAME,
    CODER_MODEL_NAME,
    TEST_RUNNER_MODEL_NAME,
    REVIEWER_MODEL_NAME,
    RECURSION_LIMIT,
)

import logging

logger = logging.getLogger(__name__)

# 加载 .env 中的环境变量
load_dotenv()


# ══════════════════════════════════════════════
# 1. State 定义
# ══════════════════════════════════════════════

class AgentState(MessagesState):
    """
    多 Agent 协作的全局共享状态。

    继承 MessagesState，自动获得：
      - messages: Annotated[list[AnyMessage], add_messages]
        所有 Agent 共用同一条消息链，保留完整上下文。

    新增自定义字段：
      - issue_task    : str   原始 Issue 描述，贯穿全程只读
      - plan          : str   Planner 输出的执行计划
      - test_output   : str   TestRunner 最新一次运行报告（pytest/脚本输出）
      - review_result : str   Reviewer 最新评审结论（"PASS" 或 "REJECT: <原因>"）
      - review_retries: int   已被打回次数（路由器用于决策是否强制结束）
      - coder_steps   : int   当前 Coder 编码轮次的 tool 调用计数（用于防死循环）
    """
    issue_task: str
    repo_language: str       # 仓库主要编程语言（如 "Python" / "TypeScript" / "Go"）
    plan: str
    test_output: str
    review_result: str
    review_retries: int
    coder_steps: int


# ══════════════════════════════════════════════
# 2. 工具列表 & LLM 初始化
# ══════════════════════════════════════════════

# Coder 可用的全量工具：文件读写 + 代码库检索
TOOLS = [
    # ── 文件读写 ──────────────────────────
    read_file,
    edit_file,
    write_and_replace_file,
    # ── 代码库检索 ────────────────────────
    list_directory,     # 查看目录树，定位项目结构
    search_codebase,    # grep 式全局正则搜索
    find_definition,    # AST 精准定位函数/类定义
    grep_in_file,       # 单文件内带上下文搜索
    # ── Import 验证 ───────────────────────
    verify_importable,  # 验证修改后的模块是否可正常导入
]

# TestRunner 专属工具：只允许执行代码，不允许写文件
TEST_RUNNER_TOOLS = [run_pytest, run_python_script, run_test_command]

# Reviewer 只需只读工具，不需要写权限
REVIEWER_TOOLS = [read_file, list_directory, grep_in_file]

# 各 Agent 专属基础 LLM（streaming=True 以支持 token 级流式输出）
# 使用 OPENAI_API_KEY / OPENAI_BASE_URL 兼容 zenmux 等 Anthropic 兼容代理
_anthropic_kwargs = dict(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or "https://api.anthropic.com",
)
_llm_planner     = ChatAnthropic(model=PLANNER_MODEL_NAME,     temperature=0, streaming=True, **_anthropic_kwargs)
_llm_coder_base  = ChatAnthropic(model=CODER_MODEL_NAME,       temperature=0, streaming=True, **_anthropic_kwargs)
_llm_runner_base = ChatAnthropic(model=TEST_RUNNER_MODEL_NAME, temperature=0, streaming=True, **_anthropic_kwargs)
_llm_review_base = ChatAnthropic(model=REVIEWER_MODEL_NAME,    temperature=0, streaming=True, **_anthropic_kwargs)

# 绑定工具的专属 LLM（模块级缓存，避免每次调用重复 bind_tools）
_llm_with_tools  = _llm_coder_base.bind_tools(TOOLS)             # Coder：全量工具
_llm_test_runner = _llm_runner_base.bind_tools(TEST_RUNNER_TOOLS) # TestRunner：执行工具
_llm_reviewer    = _llm_review_base.bind_tools(REVIEWER_TOOLS)    # Reviewer：只读工具

# 对应的 ToolNode（同样模块级缓存）
_test_runner_tool_node = ToolNode(tools=TEST_RUNNER_TOOLS)
_reviewer_tool_node    = ToolNode(tools=REVIEWER_TOOLS)


# ══════════════════════════════════════════════
# 3. 系统提示词
# ══════════════════════════════════════════════

PLANNER_SYSTEM_PROMPT = """You are a senior software architect responsible for analyzing GitHub Issues and creating detailed code modification plans.

## Your Responsibility
Based on the Issue description, output a structured execution plan for the Coder Agent to follow.

## Output Format (strictly required)
Use Markdown list format, for example:

### Execution Plan

**Target File:** `<file path>`

**Steps:**
1. <specific action 1>
2. <specific action 2>
...

**Code Standards:**
- Follow the idiomatic conventions of the target repository's language (e.g. Python type hints/docstrings, TypeScript interfaces, Go error returns)
- Handle edge cases and error conditions
- Only modify necessary files; do not introduce unrelated changes

The plan must be directly actionable with no vague descriptions."""


CODER_SYSTEM_PROMPT = """You are a professional software engineer responsible for locating and fixing bugs in real codebases.

## Available Tools
### Codebase Search (use these first to understand the codebase)
- `list_directory(directory_path, max_depth)`: View directory structure to understand project layout
- `search_codebase(pattern, directory_path, file_extension)`: Regex search for function calls/variables/imports
- `find_definition(symbol_name, directory_path)`: AST-based precise location of function or class definitions (no false positives)
- `grep_in_file(file_path, pattern, context_lines)`: Search within a single file with surrounding context

### File Operations (use after locating the bug)
- `read_file(file_path)`: Read the complete contents of a file
- `edit_file(file_path, old_string, new_string)`: **Exact replacement** of a text segment (old_string → new_string)
- `write_and_replace_file(file_path, content)`: Create a new file or completely overwrite an existing one

## ⚠️ Important Rules

### Always use edit_file to modify files
- When modifying an existing file, **you must use `edit_file`** with the exact original snippet and the replacement snippet.
- `old_string` must exactly match the file content (including indentation and whitespace). Use `read_file` or `grep_in_file` to confirm the original text first.
- **`old_string` must appear exactly once in the file.** If the target snippet appears multiple times, the tool will reject the call. Add more surrounding context lines to make it unique. For multiple similar locations, call `edit_file` separately for each with sufficient context.
- **Never** use `write_and_replace_file` on existing files — large files will be truncated and content lost.
- `write_and_replace_file` is only for creating new files.

### Do not modify test files
- **Never** modify or create any test files under the tests/ directory. The tool will reject write operations on test files.
- If the tool returns a rejection saying test file modification is not allowed, **do not retry** and do not attempt to create new test files.
- Your job is to fix the source code to pass existing tests, not to change tests to fit your code.

### Verify imports after modifying source files
- After every modification to a .py source file (non-test), **immediately** call `verify_importable("<file_path>")` to confirm the module imports cleanly.
- If it returns `[FAILED]` or `[TIMEOUT]`, fix the import error before proceeding.
- Common pitfall: moving `from xxx import yyy` from inside a function to the module top level can introduce circular imports; if unsure, leave it inside the function.

## Recommended Workflow
1. `list_directory` → understand overall project structure
2. `search_codebase` or `find_definition` → locate relevant files and functions
3. `grep_in_file` or `read_file` → read specific code and understand context
4. Analyze root cause and determine the minimal fix
5. `edit_file` → apply precise replacements
6. `read_file` → verify the change is correct
7. Output a completion report

## Code Quality Requirements
- Follow the existing code style of the target repository
- Handle edge cases
- Only modify necessary code; do not introduce unrelated changes
- Keep changes small and precise

After finishing, output a concise completion report (do not paste code — just describe what was changed and why)."""


TEST_RUNNER_SYSTEM_PROMPT = """You are an automated test executor responsible for running code and collecting results.

## Available Tools
- `run_pytest(test_path, extra_args, working_directory)`: pytest test suite for Python projects
- `run_python_script(script_path, script_args, working_directory)`: Run a single Python script
- `run_test_command(command, working_directory)`: Native test commands for any language (npm/cargo/go/make, etc.)

## ⚠️ Key Decision: Detect project type before choosing how to test

**Step 1: Identify the project language**
- `package.json` in root → Node.js/TypeScript project
- `Cargo.toml` in root → Rust project
- `go.mod` in root → Go project
- `pom.xml` or `build.gradle` in root → Java/Kotlin project
- `*.py` / `requirements.txt` / `pyproject.toml` in root → Python project

**Step 2: Choose the test command based on project type**

| Project Type   | Preferred Command                     |
|----------------|---------------------------------------|
| Python         | `run_pytest` or `run_python_script`   |
| Node.js / TS   | `run_test_command("npm test")`        |
| Rust           | `run_test_command("cargo test")`      |
| Go             | `run_test_command("go test ./...")`   |
| Java (Maven)   | `run_test_command("mvn test")`        |
| Java (Gradle)  | `run_test_command("gradle test")`     |
| Other          | Try `run_test_command("make test")`   |

## Output Format

```
[TEST EXECUTION REPORT]
Project Type: <detected language>
Command: <actual command executed>
Result: ✅ PASSED / ❌ FAILED / ⏰ TIMEOUT / ⏭️ SKIPPED (reason)
Details:
<key output lines>
```

Do not modify any files. Your only job is to execute and report."""


REVIEWER_SYSTEM_PROMPT = """You are a strict code reviewer responsible for evaluating code using automated test results and static analysis.

## Information Sources (by priority)
1. **Test execution report** (most important): TestRunner has already run the tests; results are in the message history
2. **Static analysis**: Use the read_file tool to inspect code logic

## Review Steps
1. **First check if Coder modified any test files** (tests/ directory or files with test_ / _test in the name)
2. **Check the TestRunner report**: Read TestRunner's output in the message history carefully; note PASSED / FAILED / ERROR counts
3. Use read_file to read target files for static analysis
4. Combine the above and produce your verdict

## Review Criteria
- [ ] **(Highest priority) Did Coder modify test files?** If the message history shows any write operation on files under tests/ or matching test_*.py / *_test.py, **immediately REJECT** with reason "modifying test files is not allowed"
- [ ] **(Mandatory) TestRunner report has patch-related test failures → must REJECT**: If TestRunner output contains FAILED / ERROR / non-zero exit, output REJECT and cite the specific failing test names. Do not override a test failure with "the code logic looks correct."
- [ ] **(Mandatory) Known environment noise must be filtered and must NOT trigger REJECT**: Before applying the above rule, exclude the following known test environment compatibility issues that are unrelated to the Coder's changes. **These must never be used as a reason to REJECT:**
  - `pytest.PytestConfigWarning: Unknown config option: <name>` (legacy option in test config, unrelated to code changes)
  - `AttributeError: module 'pytest' has no attribute 'RemovedInPytest4Warning'` (deprecated warning type removed in pytest 4.x)
  - `INTERNALERROR` where the only root cause in the stack trace is one of the above two
  **Mandatory handling when the above occurs:** Use read_file to read the files Coder modified and judge based purely on static code logic. If the change correctly implements the Issue requirement, **you must output PASS** — do not reject a correct fix due to environment noise.
- [ ] **(Mandatory) No PASS_TO_PASS tests at all → must REJECT**: If TestRunner output has zero PASSED records and the project has test files, treat it as a module import crash. REJECT with reason: "Suspected module import failure: TestRunner output has no PASSED records — verify modified files with verify_importable."
  **⚠️ Exception**: If the only reason TestRunner completely failed is the environment noise listed above, this rule does not apply; fall back to static code analysis.
- [ ] Python project with passing tests → positive signal; non-Python project (Node.js/Rust etc.) with skipped tests → no penalty
- [ ] pytest failure with reason "module not found / not a Python project" → ignore, not a basis for REJECT
- [ ] Files were correctly created or modified
- [ ] All required functionality is implemented
- [ ] Code logic matches the Issue requirements
- [ ] Edge cases are handled

## Output Format (strictly required — exactly one of the two)

If the review passes:
```
PASS
Reason: <brief explanation including whether tests passed>
```

If the review fails:
```
REJECT: <precisely describe the problem: test failure or code defect? which function/line? what change is expected>
```

You must read the files before reaching a conclusion. Do not guess."""


# ══════════════════════════════════════════════
# 4. 辅助函数：消息处理
# ══════════════════════════════════════════════

# 各 Agent 的命名摘要消息（保留这些消息以维持上下文连续性）
_SUMMARY_MESSAGE_NAMES = {"Planner", "TestRunner", "Reviewer"}


def _ensure_ends_with_user(messages: list) -> list:
    """
    确保消息列表最后一条是 user 消息（HumanMessage 或 ToolMessage）。

    Anthropic API 不允许 "assistant message prefill"：
    若 messages 以 AIMessage 结尾，模型会拒绝请求。
    OpenAI 不校验此规则，但 Anthropic 严格执行。
    遇到末尾为 AIMessage 时，追加一条桥接 HumanMessage 并记录警告。
    """
    if not messages:
        return messages
    last = messages[-1]
    if isinstance(last, AIMessage):
        logger.warning(
            "  [_ensure_ends_with_user] 末尾为 AIMessage（name=%s），追加桥接 HumanMessage",
            getattr(last, "name", None),
        )
        return list(messages) + [HumanMessage(content="请继续。")]
    return messages


def _estimate_messages_chars(messages: list) -> int:
    """估算消息总字符数（仅累加 content 字段）。"""
    total = 0
    for m in messages:
        content = getattr(m, "content", "")
        if isinstance(content, str):
            total += len(content)
    return total


def _extract_text(content) -> str:
    """
    将 LLM 响应的 content 统一转为纯文本字符串。

    OpenAI 的 AIMessage.content 始终是 str；
    Anthropic 的 AIMessage.content 可能是 list（多个 content blocks），
    例如 [{"type": "text", "text": "..."}] 或混合了 tool_use block。
    此函数提取所有 text block 并拼接，过滤掉 tool_use block。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in content
            if not (isinstance(b, dict) and b.get("type") == "tool_use")
        )
    return str(content) if content else ""


def _compress_messages(messages: list) -> list:
    """
    压缩消息历史：仅保留 HumanMessage（原始需求）和各 Agent 的命名摘要消息。

    丢弃所有 ToolMessage / 工具调用 AIMessage / 普通 AIMessage 中间步骤，
    防止长流水线下 context 无界增长导致 token 成本爆炸。
    """
    return [
        msg for msg in messages
        if isinstance(msg, HumanMessage)
        or (hasattr(msg, "name") and getattr(msg, "name", None) in _SUMMARY_MESSAGE_NAMES)
    ]


# ══════════════════════════════════════════════
# 5. Nodes 定义
# ══════════════════════════════════════════════

def planner_node(state: AgentState) -> dict:
    """
    Planner 节点：分析 Issue，输出结构化执行计划。

    - 读取 issue_task 字段（原始需求）
    - 调用无工具 LLM，生成 Markdown 格式的执行计划
    - 将计划写入 state["plan"] 并追加到 messages

    Args:
        state: 当前 AgentState

    Returns:
        更新 plan 和 messages 的状态字典
    """
    logger.info("📋 [Node: planner_node] Planner 开始拆解任务...")

    lang = state.get("repo_language", "Unknown") or "Unknown"
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"目标仓库编程语言：{lang}\n\n"
            f"请根据以下 Issue 制定详细执行计划：\n\n{state['issue_task']}"
        )),
    ]

    response: AIMessage = _llm_planner.invoke(_ensure_ends_with_user(messages))
    plan_text: str = response.content

    logger.info(f"📋 [Node: planner_node] 计划制定完成（{len(plan_text)} 字符）")
    logger.debug(f"  计划预览: {plan_text[:120]}...")

    return {
        "plan": plan_text,
        # 将 Planner 的计划作为 AI 消息追加到共享消息链。
        # rstrip() 避免 Anthropic API 报 "final assistant content cannot end with trailing whitespace"。
        # 紧跟一条 HumanMessage，确保消息链以 user 结尾，满足 Anthropic API
        # "conversation must end with a user message" 的约束（OpenAI 不校验此规则）。
        "messages": [
            AIMessage(content=f"【Planner 执行计划】\n\n{plan_text}".rstrip(), name="Planner"),
            HumanMessage(content="请按照上述执行计划开始修复 Bug。"),
        ],
    }


def coder_node(state: AgentState) -> dict:
    """
    Coder 节点（ReAct 推理阶段）：按计划调用工具写代码。

    - 如果是被 Reviewer 打回重做，会将打回原因注入上下文
    - 调用绑定了工具的 LLM，可能触发工具调用或输出最终报告

    Args:
        state: 当前 AgentState

    Returns:
        更新 messages 的状态字典
    """
    retries = state.get("review_retries", 0)
    review_result = state.get("review_result", "")

    # 判断是否刚从 tool_node 回来（ToolMessage 是最后一条消息）
    # 只有从 reviewer 打回进入 coder 时才是"新重试入口"；
    # tool_node → coder_node 的回调不算新重试，步数应继续累加，
    # 否则 coder_steps 永远重置为 1，MAX_CODER_STEPS 限制永远不会触发。
    last_msg = state["messages"][-1] if state["messages"] else None
    coming_from_tool = isinstance(last_msg, ToolMessage)

    is_retry = retries > 0 and review_result.startswith("REJECT") and not coming_from_tool

    if is_retry:
        logger.info(f"🔄 [Node: coder_node] 第 {retries} 次被打回，重新编码...")
        logger.debug(f"  Reviewer 反馈: {review_result[:100]}")
        new_coder_steps = 1  # 重置步数计数器
    else:
        if not coming_from_tool:
            logger.info("💻 [Node: coder_node] Coder 开始编写代码...")
        new_coder_steps = state.get("coder_steps", 0) + 1

    # 构建上下文：系统提示 + 消息历史
    if is_retry:
        # 打回重做时压缩消息历史：只保留 Issue 原文 + 各 Agent 的命名摘要消息，
        # 丢弃上一轮所有工具调用 / ToolMessage 等中间步骤，防止 context 无界增长。
        compressed = _compress_messages(state["messages"])
        rejection_reason = review_result[len("REJECT:"):].strip()
        messages = (
            [SystemMessage(content=CODER_SYSTEM_PROMPT)]
            + compressed
            + [HumanMessage(content=(
                f"⚠️ 代码评审未通过，请修复以下问题后重新写入文件：\n\n{rejection_reason}\n\n"
                "重要提醒：\n"
                "- 你只能修改源码文件，不能修改或创建任何测试文件\n"
                "- 专注于修复 Reviewer 指出的具体代码问题\n"
                "- 修复完成后立即输出完成报告，不要做多余的搜索"
            ))]
        )
        logger.debug(f"  [coder_node] 消息历史已压缩: {len(state['messages'])} → {len(compressed)} 条（丢弃工具调用中间步骤）")
    else:
        # 即使非重做路径，长链工具调用也可能导致 messages 膨胀。
        # 进入节点时若总字符数超阈值，按相同策略硬压缩，保护成本上限。
        history = state["messages"]
        total_chars = _estimate_messages_chars(history)
        if total_chars > MAX_MESSAGE_CHARS:
            compressed = _compress_messages(history)
            logger.warning(
                "  [coder_node] messages 字符数 %d 超过阈值 %d，硬压缩: %d → %d 条",
                total_chars, MAX_MESSAGE_CHARS, len(history), len(compressed),
            )
            history = compressed
        messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + history

    response = _llm_with_tools.invoke(_ensure_ends_with_user(messages))

    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_names = [tc["name"] for tc in response.tool_calls]
        logger.debug(f"🔧 [Node: coder_node] 调用工具: {tool_names}")
    else:
        logger.info("✅ [Node: coder_node] 代码编写完成，等待 Reviewer 评审")

    return {"messages": [response], "coder_steps": new_coder_steps}


def test_runner_node(state: AgentState) -> dict:
    """
    TestRunner 节点：自动执行测试/脚本，收集真实运行结果。

    职责：
      - 判断应运行 pytest 还是直接执行脚本
      - 调用 run_pytest / run_python_script 工具（内部 ReAct 循环）
      - 将测试输出写入 state["test_output"]，供 Reviewer 参考

    Args:
        state: 当前 AgentState

    Returns:
        更新 test_output 和 messages 的状态字典
    """
    logger.info("🧪 [Node: test_runner_node] TestRunner 开始执行测试...")

    messages = [
        SystemMessage(content=TEST_RUNNER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Planner 的执行计划：\n{state.get('plan', '无计划')}\n\n"
            "请根据计划决定运行哪些测试，然后执行并给出测试执行报告。\n"
            "工作目录为项目根目录（当前目录）。"
        )),
    ]

    current_messages = list(messages)
    test_report: str = ""

    # TestRunner 内部 ReAct 循环：执行工具 → 收集结果 → 输出报告
    for _round in range(8):  # 最多 8 轮，防止意外死循环
        resp = _llm_test_runner.invoke(_ensure_ends_with_user(current_messages))
        current_messages.append(resp)

        if hasattr(resp, "tool_calls") and resp.tool_calls:
            tool_names = [tc["name"] for tc in resp.tool_calls]
            logger.debug(f"  [TestRunner 内部] 执行工具: {tool_names}")
            tool_result_state = _test_runner_tool_node.invoke({"messages": current_messages})
            new_tool_msgs = tool_result_state["messages"]
            current_messages.extend(new_tool_msgs)
        else:
            # LLM 已输出最终报告
            test_report = _extract_text(resp.content).strip()
            break

    if not test_report:
        test_report = "[TestRunner] 未能生成测试报告（可能超出循环次数）"

    logger.info(f"🧪 [Node: test_runner_node] 测试完成，报告长度: {len(test_report)} 字符")
    # 预览关键行（PASSED/FAILED/ERROR）
    key_lines = [l for l in test_report.splitlines() if any(
        kw in l.upper() for kw in ["PASS", "FAIL", "ERROR", "EXIT"]
    )]
    if key_lines:
        logger.debug(f"  关键行: {key_lines[:3]}")

    return {
        "test_output": test_report,
        "messages": [
            AIMessage(
                content=f"【TestRunner 执行报告】\n\n{test_report}".rstrip(),
                name="TestRunner",
            )
        ],
    }


def reviewer_node(state: AgentState) -> dict:
    """
    Reviewer 节点：结合 TestRunner 报告 + 静态检查做代码评审。

    - 消息历史中已包含 TestRunner 的执行报告（test_output）
    - 使用绑定了只读工具的 LLM，进一步做静态代码检查
    - 输出严格的 PASS 或 REJECT: <原因> 结论
    - 将结论写入 state["review_result"]

    Args:
        state: 当前 AgentState

    Returns:
        更新 review_result 和 messages 的状态字典
    """
    logger.info("🔍 [Node: reviewer_node] Reviewer 开始评审代码...")

    test_output = state.get("test_output", "").strip()
    test_section = (
        f"## TestRunner 自动测试结果\n\n{test_output}"
        if test_output
        else "## TestRunner 自动测试结果\n\n（本次未运行测试）"
    )

    messages = [
        SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"原始 Issue 需求：\n{state['issue_task']}\n\n"
            f"Planner 制定的执行计划：\n{state.get('plan', '无计划')}\n\n"
            f"{test_section}\n\n"
            "请结合上方测试结果和静态代码检查，给出 PASS 或 REJECT 结论。"
        )),
    ]

    # Reviewer 可能需要多轮（先 read_file，再给结论）
    current_messages = list(messages)
    tool_call_total = 0  # 累计工具调用次数（防止多轮内单轮多调用导致总量失控）

    for _round in range(5):  # 最多 5 轮内部循环防止意外死循环
        # 工具调用总数已超上限：强制要求 LLM 不再调用工具，直接给结论
        if tool_call_total >= MAX_REVIEWER_TOOL_CALLS:
            logger.warning(
                "  [Reviewer 内部] 工具调用已达上限 %d，强制要求输出结论",
                MAX_REVIEWER_TOOL_CALLS,
            )
            current_messages.append(HumanMessage(content=(
                "⚠️ 工具调用次数已达上限，请立即基于现有信息输出 PASS 或 REJECT 结论，"
                "不要再调用任何工具。"
            )))
            # 用无工具版本的 LLM 强制收束
            resp = _llm_review_base.invoke(_ensure_ends_with_user(current_messages))
            current_messages.append(resp)
            break

        resp = _llm_reviewer.invoke(_ensure_ends_with_user(current_messages))
        current_messages.append(resp)

        if hasattr(resp, "tool_calls") and resp.tool_calls:
            # 执行工具调用（通常是 read_file）
            tool_call_total += len(resp.tool_calls)
            tool_result_state = _reviewer_tool_node.invoke({"messages": current_messages})
            # ToolNode 返回包含 ToolMessage 的消息列表
            new_tool_msgs = tool_result_state["messages"]
            current_messages.extend(new_tool_msgs)
            tool_names = [tc["name"] for tc in resp.tool_calls]
            logger.debug(f"  [Reviewer 内部] 执行工具: {tool_names}（累计 {tool_call_total}/{MAX_REVIEWER_TOOL_CALLS}）")
        else:
            # LLM 输出了最终结论，退出循环
            break

    # 提取最终结论（最后一条 AI 消息的内容）
    conclusion: str = _extract_text(resp.content).strip()
    # LLM 经常在结论外包裹 Markdown 标题（"### 评审结论"）或代码围栏（```），
    # 需要先剥离再判断 PASS/REJECT。
    _lines = conclusion.splitlines()
    _stripped_lines = [
        l for l in _lines
        if not l.strip().startswith("#") and not l.strip().startswith("```")
    ]
    _conclusion_inner = "\n".join(_stripped_lines).strip()
    is_pass = _conclusion_inner.upper().startswith("PASS")

    if is_pass:
        logger.info(f"✅ [Node: reviewer_node] 评审结论: {conclusion[:100]}")
    else:
        logger.error(f"❌ [Node: reviewer_node] 评审结论: {conclusion[:100]}")

    # 更新打回次数（仅 REJECT 时递增）
    current_retries = state.get("review_retries", 0)
    new_retries = current_retries if is_pass else current_retries + 1

    return {
        "review_result": conclusion,
        "review_retries": new_retries,
        "messages": [
            AIMessage(
                content=f"【Reviewer 评审结论】\n\n{conclusion}".rstrip(),
                name="Reviewer",
            )
        ],
    }


# ══════════════════════════════════════════════
# 5. 条件路由函数
# ══════════════════════════════════════════════

def coder_should_continue(
    state: AgentState,
) -> Literal["tool_node", "test_runner_node"]:
    """
    Coder 完成一轮后的路由：
      - 如果最新消息包含 tool_calls 且未超步数上限 → 执行工具，继续 ReAct 循环
      - 超出步数上限 → 强制进入 TestRunner（防止死循环）
      - 否则（Coder 完成编码）→ 进入 TestRunner 运行测试
    """
    last_message = state["messages"][-1]
    coder_steps = state.get("coder_steps", 0)

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if coder_steps >= MAX_CODER_STEPS:
            logger.warning(f"⚠️ [Router: coder] Coder 已执行 {coder_steps} 步，达到上限，强制进入测试 → test_runner_node")
            return "test_runner_node"
        logger.debug("🔀 [Router: coder] 有工具调用 → tool_node")
        return "tool_node"
    logger.debug("🔀 [Router: coder] 编码完成 → test_runner_node")
    return "test_runner_node"


def reviewer_should_continue(
    state: AgentState,
) -> Literal["coder_node", END]:
    """
    Reviewer 评审后的路由：
      - PASS 或已超出最大打回次数 → END
      - REJECT 且未超出限制     → 打回 coder_node 重做
    """
    review_result = state.get("review_result", "")
    retries = state.get("review_retries", 0)

    # 剥离 Markdown 标题和代码围栏后再判断 PASS
    _inner = "\n".join(
        l for l in review_result.splitlines()
        if not l.strip().startswith("#") and not l.strip().startswith("```")
    ).strip()
    if _inner.upper().startswith("PASS"):
        logger.debug("🏁 [Router: reviewer] 评审通过 → END")
        return END

    if retries >= MAX_REVIEW_RETRIES:
        logger.warning(f"⚠️ [Router: reviewer] 已打回 {retries} 次，强制结束 → END")
        return END

    logger.debug(f"🔄 [Router: reviewer] 评审未通过（第 {retries} 次打回） → coder_node")
    return "coder_node"


# ══════════════════════════════════════════════
# 6. Graph 构建与编译
# ══════════════════════════════════════════════

def build_graph(checkpointer=None):
    """
    组装四阶段多 Agent 协作的 LangGraph StateGraph。

    完整图结构：

        START
          │
          ▼
      planner_node              ← 拆解任务，产出 plan
          │
          ▼
       coder_node  ◄────────────────────────────────────────┐
          │                                                  │
          │ (coder_should_continue)                          │ (REJECT & retries < MAX)
          ├── has tool_calls ──► tool_node ──► coder_node   │
          │                                                  │
          └── no tool_calls ──► test_runner_node             │
                                       │                     │
                                       ▼ (无条件)             │
                                  reviewer_node ─────────────┘
                                       │
                                       │ (reviewer_should_continue)
                                       ├── PASS ──► END
                                       └── REJECT (≥MAX) ──► END

    Args:
        checkpointer: 可选的 LangGraph checkpointer（如 PostgresSaver）。
                      提供时每个节点完成后自动持久化状态，支持断点续传。
                      不提供时行为与原来相同（无持久化）。

    Returns:
        编译好的 CompiledGraph（Runnable）
    """
    graph = StateGraph(AgentState)

    # ── 添加节点 ──
    graph.add_node("planner_node", planner_node)
    graph.add_node("coder_node", coder_node)
    graph.add_node("tool_node", ToolNode(tools=TOOLS))        # Coder 全量工具集
    graph.add_node("test_runner_node", test_runner_node)      # 自动运行测试
    graph.add_node("reviewer_node", reviewer_node)            # 结合测试结果评审

    # ── 添加边 ──
    # 入口
    graph.add_edge(START, "planner_node")
    # Planner → Coder
    graph.add_edge("planner_node", "coder_node")

    # Coder：有工具调用 → tool_node，完成编码 → test_runner_node
    graph.add_conditional_edges(
        "coder_node",
        coder_should_continue,
        {
            "tool_node": "tool_node",
            "test_runner_node": "test_runner_node",
        },
    )

    # tool_node 执行完毕 → 回 Coder 继续 ReAct 循环
    graph.add_edge("tool_node", "coder_node")

    # test_runner_node 完成 → 无条件进入 Reviewer
    graph.add_edge("test_runner_node", "reviewer_node")

    # Reviewer：通过 → END，打回 → Coder 重做
    graph.add_conditional_edges(
        "reviewer_node",
        reviewer_should_continue,
        {
            "coder_node": "coder_node",
            END: END,
        },
    )

    logger.info("📦 [Graph] 四阶段 StateGraph 构建完成，正在编译...")
    compiled = graph.compile(checkpointer=checkpointer)
    cp_label = type(checkpointer).__name__ if checkpointer else "无"
    logger.info(f"✅ [Graph] 编译成功！Checkpointer={cp_label}  流程: START→Planner→Coder⇄Tools→TestRunner→Reviewer→END")
    return compiled


# ── 模块级全局实例（供外部 import 直接使用，无 checkpointer）──
# server.py 在 startup 中会用 PostgresSaver 重新构建带持久化的实例。
app = build_graph()
# 推荐的运行时配置（recursion_limit 防止复杂任务被截断）
APP_CONFIG = {"recursion_limit": RECURSION_LIMIT}
