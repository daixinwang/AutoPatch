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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
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
from tools.execute_tools import run_pytest, run_python_script, run_test_command
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
]

# TestRunner 专属工具：只允许执行代码，不允许写文件
TEST_RUNNER_TOOLS = [run_pytest, run_python_script, run_test_command]

# Reviewer 只需只读工具，不需要写权限
REVIEWER_TOOLS = [read_file, list_directory, grep_in_file]

# 各 Agent 专属基础 LLM（streaming=True 以支持 token 级流式输出）
_llm_planner     = ChatOpenAI(model=PLANNER_MODEL_NAME,     temperature=0, streaming=True)
_llm_coder_base  = ChatOpenAI(model=CODER_MODEL_NAME,       temperature=0, streaming=True)
_llm_runner_base = ChatOpenAI(model=TEST_RUNNER_MODEL_NAME, temperature=0, streaming=True)
_llm_review_base = ChatOpenAI(model=REVIEWER_MODEL_NAME,    temperature=0, streaming=True)

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

PLANNER_SYSTEM_PROMPT = """你是一个资深技术架构师，负责分析 GitHub Issue 并制定详细的代码修改计划。

## 你的职责
根据 Issue 描述，输出一份结构清晰的执行计划，供后续的 Coder Agent 执行。

## 输出格式（必须严格遵守）
用 Markdown 列表输出，例如：

### 执行计划

**目标文件：** `<文件路径>`

**步骤：**
1. <具体操作步骤1>
2. <具体操作步骤2>
...

**代码规范要求：**
- 遵循目标仓库语言的惯用规范（如 Python 的类型注解/docstring、TypeScript 的接口定义、Go 的错误返回等）
- 处理边界条件和异常情况
- 只修改必要的文件，不引入无关改动

计划必须可直接执行，不要包含模糊描述。"""


CODER_SYSTEM_PROMPT = """你是一个专业的软件工程师，负责在真实代码库中定位 Bug 并修复它。

## 可用工具
### 代码库检索（先用这些工具理解代码库）
- `list_directory(directory_path, max_depth)`: 查看目录结构，了解项目布局
- `search_codebase(pattern, directory_path, file_extension)`: 正则搜索代码库，找函数调用/变量/import
- `find_definition(symbol_name, directory_path)`: AST 精准定位函数或类的定义（无误报）
- `grep_in_file(file_path, pattern, context_lines)`: 在单文件内搜索，带上下文代码段

### 文件操作（找到 Bug 后再用这些工具）
- `read_file(file_path)`: 读取文件完整内容
- `edit_file(file_path, old_string, new_string)`: **精确替换**文件中的一段文本（old_string → new_string）
- `write_and_replace_file(file_path, content)`: 创建新文件，或完整覆盖写入文件

## ⚠️ 重要规则

### 编辑文件必须使用 edit_file
- 修改已有文件时，**必须使用 `edit_file`**，提供要替换的原始代码片段和修改后的代码片段。
- `old_string` 必须与文件内容完全匹配（包括缩进和空白字符），建议先用 `read_file` 或 `grep_in_file` 确认原文。
- **`old_string` 必须在文件中唯一出现。** 如果目标代码片段在文件中出现多次，工具会拒绝执行。此时你需要在 `old_string` 中包含更多上下文（如前后几行代码）来唯一定位。如果需要修改多处相似代码，请对每一处分别调用 `edit_file`，每次提供足够的上下文。
- **禁止**对已有文件使用 `write_and_replace_file`，因为大文件会导致内容截断丢失。
- `write_and_replace_file` 仅用于创建新文件。

### 不要修改测试文件
- **禁止**修改或创建 tests/ 目录下的任何测试文件。工具会拒绝对测试文件的写操作。
- 如果工具返回了"不允许修改测试文件"的拒绝信息，**不要重试**，也不要尝试创建新的测试文件。
- 你的任务是修复源码使其通过现有测试，不是修改测试来适配你的代码。

## 推荐工作流程
1. `list_directory` → 了解项目整体结构
2. `search_codebase` 或 `find_definition` → 定位相关文件和函数
3. `grep_in_file` 或 `read_file` → 阅读具体代码，理解上下文
4. 分析根因，确定最小修改方案
5. `edit_file` → 精确替换需要修改的代码片段
6. `read_file` → 验证修改正确
7. 输出完成报告

## 代码质量要求
- 遵循目标仓库的现有代码风格
- 必须处理边界情况
- 只修改必要的代码，不引入无关改动
- 修改应尽量小而精确

完成后输出简洁的完成报告（不要重复贴代码，只说明改了什么、为什么这样改）。"""


TEST_RUNNER_SYSTEM_PROMPT = """你是一个自动化测试执行器，负责运行代码并收集执行结果。

## 可用工具
- `run_pytest(test_path, extra_args, working_directory)`: Python 项目 pytest 测试套件
- `run_python_script(script_path, script_args, working_directory)`: 运行单个 Python 脚本
- `run_test_command(command, working_directory)`: 各语言原生测试命令（npm/cargo/go/make 等）

## ⚠️ 关键决策：先判断项目类型，再决定如何测试

**第一步：判断项目语言**
- 根目录有 `package.json` → Node.js/TypeScript 项目
- 根目录有 `Cargo.toml` → Rust 项目
- 根目录有 `go.mod` → Go 项目
- 根目录有 `pom.xml` 或 `build.gradle` → Java/Kotlin 项目
- 根目录有 `*.py` / `requirements.txt` / `pyproject.toml` → Python 项目

**第二步：根据项目类型选择测试命令**

| 项目类型       | 首选命令                              |
|----------------|---------------------------------------|
| Python         | `run_pytest` 或 `run_python_script`   |
| Node.js / TS   | `run_test_command("npm test")`        |
| Rust           | `run_test_command("cargo test")`      |
| Go             | `run_test_command("go test ./...")`   |
| Java (Maven)   | `run_test_command("mvn test")`        |
| Java (Gradle)  | `run_test_command("gradle test")`     |
| 其他           | 尝试 `run_test_command("make test")`  |

## 输出格式

```
【测试执行报告】
项目类型: <检测到的语言>
执行命令: <实际执行的命令>
结果: ✅ 通过 / ❌ 失败 / ⏰ 超时 / ⏭️ 跳过（原因）
说明:
<关键输出行>
```

不要修改任何文件，只负责执行和报告。"""


REVIEWER_SYSTEM_PROMPT = """你是一位严格的代码 Reviewer，负责结合自动化测试结果和静态检查来评审代码。

## 评审信息来源（按优先级）
1. **测试执行报告**（最重要）：TestRunner 已自动运行了测试，结果在消息历史中
2. **静态检查**：使用 read_file 工具读取文件，检查代码逻辑

## 评审步骤
1. **首先检查消息历史中 Coder 是否修改了测试文件**（tests/ 目录或文件名含 test_ / _test 的文件）
2. **检查 TestRunner 报告**：仔细阅读消息历史中 TestRunner 的测试输出，记录 PASSED / FAILED / ERROR 数量
3. 使用 read_file 读取目标文件做静态检查
4. 综合上述信息，给出评审结论

## 评审标准
- [ ] **（最优先）Coder 是否修改了测试文件？** 若消息历史中出现对 tests/ 下文件或 test_*.py / *_test.py 的写操作，**立即 REJECT**，原因写明"不允许修改测试文件"
- [ ] **（强制）TestRunner 报告任意测试失败 → 必须 REJECT**：若 TestRunner 输出中包含 FAILED / ERROR / exit 非 0，无论静态检查结论如何，必须输出 REJECT，并在原因中引用具体失败的测试名称。禁止用"代码逻辑看起来正确"来覆盖测试失败结论。
- [ ] **（强制）PASS_TO_PASS 测试全部缺失 → 必须 REJECT**：若 TestRunner 输出中完全没有任何 PASSED 记录，且项目存在测试文件，视为模块导入崩溃，必须 REJECT，原因写"疑似模块导入失败：TestRunner 输出无任何 PASSED 记录，请用 verify_importable 验证修改的文件"。
- [ ] 如果是 Python 项目且测试通过 → 加分；如果是非 Python 项目（Node.js/Rust 等）测试被跳过 → 不扣分
- [ ] pytest 失败且原因是"模块不存在/非Python项目" → 忽略此项，不作为 REJECT 依据
- [ ] 文件是否被正确创建或修改
- [ ] 所有要求的功能是否均已实现
- [ ] 代码逻辑是否符合 Issue 需求
- [ ] 边界情况是否处理

## 输出格式（必须严格遵守，只能二选一）

如果通过评审：
```
PASS
理由：<简短说明，包含测试是否通过的情况>
```

如果不通过：
```
REJECT: <精确指出问题：是测试失败还是代码缺陷？具体是哪个函数/行？期望如何修改>
```

你必须先读取文件再下结论，不要凭空猜测。"""


# ══════════════════════════════════════════════
# 4. 辅助函数：消息压缩
# ══════════════════════════════════════════════

# 各 Agent 的命名摘要消息（保留这些消息以维持上下文连续性）
_SUMMARY_MESSAGE_NAMES = {"Planner", "TestRunner", "Reviewer"}


def _estimate_messages_chars(messages: list) -> int:
    """估算消息总字符数（仅累加 content 字段）。"""
    total = 0
    for m in messages:
        content = getattr(m, "content", "")
        if isinstance(content, str):
            total += len(content)
    return total


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

    response: AIMessage = _llm_planner.invoke(messages)
    plan_text: str = response.content

    logger.info(f"📋 [Node: planner_node] 计划制定完成（{len(plan_text)} 字符）")
    logger.debug(f"  计划预览: {plan_text[:120]}...")

    return {
        "plan": plan_text,
        # 将 Planner 的计划作为 AI 消息追加到共享消息链
        "messages": [
            AIMessage(content=f"【Planner 执行计划】\n\n{plan_text}", name="Planner")
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

    is_retry = retries > 0 and review_result.startswith("REJECT")

    if is_retry:
        logger.info(f"🔄 [Node: coder_node] 第 {retries} 次被打回，重新编码...")
        logger.debug(f"  Reviewer 反馈: {review_result[:100]}")
        new_coder_steps = 1  # 重置步数计数器
    else:
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

    response = _llm_with_tools.invoke(messages)

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
        resp = _llm_test_runner.invoke(current_messages)
        current_messages.append(resp)

        if hasattr(resp, "tool_calls") and resp.tool_calls:
            tool_names = [tc["name"] for tc in resp.tool_calls]
            logger.debug(f"  [TestRunner 内部] 执行工具: {tool_names}")
            tool_result_state = _test_runner_tool_node.invoke({"messages": current_messages})
            new_tool_msgs = tool_result_state["messages"]
            current_messages.extend(new_tool_msgs)
        else:
            # LLM 已输出最终报告
            test_report = resp.content.strip()
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
                content=f"【TestRunner 执行报告】\n\n{test_report}",
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
            resp = _llm_review_base.invoke(current_messages)
            current_messages.append(resp)
            break

        resp = _llm_reviewer.invoke(current_messages)
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
    conclusion: str = resp.content.strip()
    # LLM 经常用 ``` 代码块包裹结论，需要先剥离再判断
    _conclusion_inner = conclusion
    if _conclusion_inner.startswith("```"):
        # 去掉首行 ``` 和末尾 ```
        lines = _conclusion_inner.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        _conclusion_inner = "\n".join(lines).strip()
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
                content=f"【Reviewer 评审结论】\n\n{conclusion}",
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

    if review_result.upper().startswith("PASS"):
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
