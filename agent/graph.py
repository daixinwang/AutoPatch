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
from tools.file_tools import read_file, write_and_replace_file
from tools.search_tools import (
    find_definition,
    grep_in_file,
    list_directory,
    search_codebase,
)
from tools.execute_tools import run_pytest, run_python_script

# 加载 .env 中的环境变量
load_dotenv()

# ══════════════════════════════════════════════
# 常量
# ══════════════════════════════════════════════

# Reviewer 最多打回几次，防止 Coder 陷入死循环
MAX_REVIEW_RETRIES: int = 3


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
    """
    issue_task: str
    plan: str
    test_output: str
    review_result: str
    review_retries: int


# ══════════════════════════════════════════════
# 2. 工具列表 & LLM 初始化
# ══════════════════════════════════════════════

# Coder 可用的全量工具：文件读写 + 代码库检索
TOOLS = [
    # ── 文件读写 ──────────────────────────
    read_file,
    write_and_replace_file,
    # ── 代码库检索 ────────────────────────
    list_directory,     # 查看目录树，定位项目结构
    search_codebase,    # grep 式全局正则搜索
    find_definition,    # AST 精准定位函数/类定义
    grep_in_file,       # 单文件内带上下文搜索
]

# TestRunner 专属工具：只允许执行代码，不允许写文件
TEST_RUNNER_TOOLS = [run_pytest, run_python_script]

# Reviewer 只需只读工具，不需要写权限
REVIEWER_TOOLS = [read_file, list_directory, grep_in_file]

_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")

# 基础 LLM（无工具绑定），供 Planner / Reviewer 使用
_llm = ChatOpenAI(model=_model_name, temperature=0, streaming=False)

# 绑定工具的 LLM，供 Coder 使用
_llm_with_tools = _llm.bind_tools(TOOLS)


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
- 所有函数必须有类型注解（Union[int, float] 或具体类型）
- 所有函数必须有 docstring
- 异常情况必须处理

计划必须可直接执行，不要包含模糊描述。"""


CODER_SYSTEM_PROMPT = """你是一个专业的 Python 开发工程师，负责在真实代码库中定位 Bug 并修复它。

## 可用工具
### 代码库检索（先用这些工具理解代码库）
- `list_directory(directory_path, max_depth)`: 查看目录结构，了解项目布局
- `search_codebase(pattern, directory_path, file_extension)`: 正则搜索代码库，找函数调用/变量/import
- `find_definition(symbol_name, directory_path)`: AST 精准定位函数或类的定义（无误报）
- `grep_in_file(file_path, pattern, context_lines)`: 在单文件内搜索，带上下文代码段

### 文件操作（找到 Bug 后再用这些工具）
- `read_file(file_path)`: 读取文件完整内容
- `write_and_replace_file(file_path, content)`: 创建或覆盖写入文件

## 推荐工作流程（真实 Bug Fix）
1. `list_directory` → 了解项目整体结构
2. `search_codebase` 或 `find_definition` → 定位相关文件和函数
3. `grep_in_file` 或 `read_file` → 阅读具体代码，理解上下文
4. 分析根因，生成修复代码
5. `write_and_replace_file` → 写入修改
6. `read_file` → 验证写入正确
7. 输出完成报告

## 代码质量要求
- 必须有类型注解和 docstring
- 必须处理边界情况
- 使用相对路径，UTF-8 编码
- 只修改必要的文件，不引入无关改动

完成后输出简洁的完成报告（不要重复贴代码，只说明改了什么、为什么这样改）。"""


TEST_RUNNER_SYSTEM_PROMPT = """你是一个自动化测试执行器，负责运行代码并收集执行结果。

## 可用工具
- `run_pytest(test_path, extra_args, working_directory)`: 运行 pytest 测试套件（仅 Python 项目）
- `run_python_script(script_path, script_args, working_directory)`: 运行单个 Python 脚本

## ⚠️ 关键决策：先判断项目类型，再决定如何测试

**第一步：判断项目语言**
- 如果根目录有 `package.json` → 这是 Node.js/TypeScript 项目，**绝对不要运行 pytest 或 python 脚本**
- 如果根目录有 `Cargo.toml` → 这是 Rust 项目，**不要运行 pytest**
- 如果根目录有 `*.py` 或 `requirements.txt` 或 `pyproject.toml` → 才是 Python 项目

**第二步：根据项目类型测试**

情况 A：Python 项目
1. 有 `tests/` 目录或 `test_*.py` 文件 → 使用 `run_pytest`
2. 没有测试文件 → 用 `run_python_script` 验证新创建的 .py 文件能正常运行

情况 B：非 Python 项目（Node.js / Rust / Go 等）
- **跳过测试执行**，直接输出报告说明原因
- 原因：本工具只支持 Python 运行时，无法运行其他语言的测试

## 输出格式

```
【测试执行报告】
项目类型: Python / Node.js / 其他
执行命令: <命令> 或 <跳过>
结果: ✅ 通过 / ❌ 失败 / ⏰ 超时 / ⏭️ 跳过（非Python项目）
说明:
<关键输出或跳过原因>
```

不要修改任何文件，只负责执行和报告。"""


REVIEWER_SYSTEM_PROMPT = """你是一位严格的代码 Reviewer，负责结合自动化测试结果和静态检查来评审代码。

## 评审信息来源（按优先级）
1. **测试执行报告**（最重要）：TestRunner 已自动运行了测试，结果在消息历史中
2. **静态检查**：使用 read_file 工具读取文件，检查代码逻辑

## 评审步骤
1. 仔细阅读消息历史中 TestRunner 的测试报告
2. 使用 read_file 读取目标文件做静态检查
3. 综合两方面信息，给出评审结论

## 评审标准
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
# 4. Nodes 定义
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
    print("\n" + "═" * 50)
    print("📋 [Node: planner_node] Planner 开始拆解任务...")

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"请根据以下 Issue 制定详细执行计划：\n\n{state['issue_task']}"
        )),
    ]

    response: AIMessage = _llm.invoke(messages)
    plan_text: str = response.content

    print(f"📋 [Node: planner_node] 计划制定完成（{len(plan_text)} 字符）")
    print(f"  计划预览: {plan_text[:120]}...")

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
    print("\n" + "─" * 50)
    retries = state.get("review_retries", 0)
    review_result = state.get("review_result", "")

    if retries > 0 and review_result.startswith("REJECT"):
        print(f"🔄 [Node: coder_node] 第 {retries} 次被打回，重新编码...")
        print(f"  Reviewer 反馈: {review_result[:100]}")
    else:
        print("💻 [Node: coder_node] Coder 开始编写代码...")

    # 构建完整上下文：系统提示 + 历史消息
    # 如果有打回记录，额外注入一条 HumanMessage 明确指出问题
    messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + state["messages"]

    if retries > 0 and review_result.startswith("REJECT"):
        rejection_reason = review_result[len("REJECT:"):].strip()
        messages.append(
            HumanMessage(
                content=(
                    f"⚠️ 代码评审未通过，请修复以下问题后重新写入文件：\n\n{rejection_reason}"
                )
            )
        )

    response = _llm_with_tools.invoke(messages)

    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_names = [tc["name"] for tc in response.tool_calls]
        print(f"🔧 [Node: coder_node] 调用工具: {tool_names}")
    else:
        print("✅ [Node: coder_node] 代码编写完成，等待 Reviewer 评审")

    return {"messages": [response]}


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
    print("\n" + "─" * 50)
    print("🧪 [Node: test_runner_node] TestRunner 开始执行测试...")

    _llm_test_runner = _llm.bind_tools(TEST_RUNNER_TOOLS)
    tool_executor = ToolNode(tools=TEST_RUNNER_TOOLS)

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
            print(f"  [TestRunner 内部] 执行工具: {tool_names}")
            tool_result_state = tool_executor.invoke({"messages": current_messages})
            new_tool_msgs = tool_result_state["messages"]
            current_messages.extend(new_tool_msgs)
        else:
            # LLM 已输出最终报告
            test_report = resp.content.strip()
            break

    if not test_report:
        test_report = "[TestRunner] 未能生成测试报告（可能超出循环次数）"

    print(f"🧪 [Node: test_runner_node] 测试完成，报告长度: {len(test_report)} 字符")
    # 预览关键行（PASSED/FAILED/ERROR）
    key_lines = [l for l in test_report.splitlines() if any(
        kw in l.upper() for kw in ["PASS", "FAIL", "ERROR", "EXIT"]
    )]
    if key_lines:
        print(f"  关键行: {key_lines[:3]}")

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
    print("\n" + "─" * 50)
    print("🔍 [Node: reviewer_node] Reviewer 开始评审代码...")

    # Reviewer 使用只读工具集（读文件 + 目录浏览 + 文件内搜索）
    _llm_reviewer = _llm.bind_tools(REVIEWER_TOOLS)

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
    # 这里用一个简单的内部循环处理工具调用
    tool_executor = ToolNode(tools=REVIEWER_TOOLS)
    current_messages = list(messages)

    for _round in range(5):  # 最多 5 轮内部循环防止意外死循环
        resp = _llm_reviewer.invoke(current_messages)
        current_messages.append(resp)

        if hasattr(resp, "tool_calls") and resp.tool_calls:
            # 执行工具调用（通常是 read_file）
            tool_result_state = tool_executor.invoke({"messages": current_messages})
            # ToolNode 返回包含 ToolMessage 的消息列表
            new_tool_msgs = tool_result_state["messages"]
            current_messages.extend(new_tool_msgs)
            tool_names = [tc["name"] for tc in resp.tool_calls]
            print(f"  [Reviewer 内部] 执行工具: {tool_names}")
        else:
            # LLM 输出了最终结论，退出循环
            break

    # 提取最终结论（最后一条 AI 消息的内容）
    conclusion: str = resp.content.strip()
    is_pass = conclusion.upper().startswith("PASS")

    print(f"{'✅' if is_pass else '❌'} [Node: reviewer_node] 评审结论: {conclusion[:100]}")

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
      - 如果最新消息包含 tool_calls → 执行工具，继续 ReAct 循环
      - 否则（Coder 完成编码）→ 进入 TestRunner 运行测试
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print("🔀 [Router: coder] 有工具调用 → tool_node")
        return "tool_node"
    print("🔀 [Router: coder] 编码完成 → test_runner_node")
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
        print("🏁 [Router: reviewer] 评审通过 → END")
        return END

    if retries >= MAX_REVIEW_RETRIES:
        print(f"⚠️ [Router: reviewer] 已打回 {retries} 次，强制结束 → END")
        return END

    print(f"🔄 [Router: reviewer] 评审未通过（第 {retries} 次打回） → coder_node")
    return "coder_node"


# ══════════════════════════════════════════════
# 6. Graph 构建与编译
# ══════════════════════════════════════════════

def build_graph():
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

    print("📦 [Graph] 四阶段 StateGraph 构建完成，正在编译...")
    compiled = graph.compile()
    print("✅ [Graph] 编译成功！流程: START→Planner→Coder⇄Tools→TestRunner→Reviewer→END")
    return compiled


def build_graph_with_config():
    """
    带运行时配置的 Graph 工厂。
    返回编译好的 Graph，并提供推荐的 invoke/stream 配置。
    """
    compiled = build_graph()
    # 推荐配置：提高递归上限，适应复杂多轮任务
    config = {"recursion_limit": 100}
    return compiled, config


# ── 模块级全局实例（供外部 import 直接使用）──
app = build_graph()
# 推荐的运行时配置（recursion_limit 防止复杂任务被截断）
APP_CONFIG = {"recursion_limit": 100}
