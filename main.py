"""
main.py
-------
AutoPatch Agent 入口文件。

用法：
    python main.py

功能：
    1. 定义测试任务（Issue 描述）
    2. 实例化并运行 LangGraph Agent
    3. 使用 stream 模式逐步打印每次状态更新，追踪 Graph 运行轨迹
"""

import sys
from langchain_core.messages import HumanMessage

# 导入编译好的 Graph 应用
from agent.graph import app, AgentState


# ══════════════════════════════════════════════
# 测试任务定义
# ══════════════════════════════════════════════

# 模拟一个 GitHub Issue 的描述
TEST_ISSUE = """
Issue #42: 项目缺少基础数学工具模块

**问题描述：**
当前项目中没有基础的数学计算工具，导致其他模块无法复用简单的计算逻辑。

**期望行为：**
请在项目根目录创建 `calc.py` 文件，实现以下功能：
1. `add(a, b)` 函数：计算两个数的和
2. `subtract(a, b)` 函数：计算两个数的差
3. `multiply(a, b)` 函数：计算两个数的积
4. `divide(a, b)` 函数：计算两个数的商（需要处理除以零的情况）

所有函数必须：
- 有完整的类型注解（支持 int 和 float）
- 有 docstring 说明
- `divide` 函数在 b 为 0 时应抛出 ValueError
"""


def print_separator(char: str = "═", width: int = 60) -> None:
    """打印分隔线，提升日志可读性。"""
    print(char * width)


def run_agent(issue_description: str) -> None:
    """
    运行 AutoPatch 多 Agent 流水线并实时打印状态流。

    流程：Planner → Coder ⇄ Tools → Reviewer（可打回 Coder）→ END

    Args:
        issue_description: 原始 Issue 描述文本
    """
    print_separator("═")
    print("🚀 AutoPatch Multi-Agent 流水线启动")
    print_separator("═")
    print(f"\n📋 任务描述:\n{issue_description.strip()}\n")
    print_separator("─")

    # 初始化状态：包含全部自定义字段的初始值
    initial_state: AgentState = {
        "messages": [
            HumanMessage(content=f"Issue 需求：\n\n{issue_description}")
        ],
        "issue_task": issue_description,
        "plan": "",
        "test_output": "",
        "review_result": "",
        "review_retries": 0,
    }

    # 节点名称 → 展示图标映射，方便日志识别
    NODE_ICONS = {
        "planner_node":      "📋 Planner",
        "coder_node":        "💻 Coder",
        "tool_node":         "🔧 Tools",
        "test_runner_node":  "🧪 TestRunner",
        "reviewer_node":     "🔍 Reviewer",
    }

    print("\n▶️  开始运行 Graph (stream 模式)...\n")

    step_count = 0
    final_output = None

    for chunk in app.stream(initial_state, stream_mode="updates"):
        step_count += 1
        print_separator("·", 40)
        print(f"📨 [Step {step_count}] 状态更新:")

        for node_name, node_output in chunk.items():
            icon = NODE_ICONS.get(node_name, f"[{node_name}]")
            print(f"  来源节点: {icon}")

            # 打印新增的自定义状态字段变化
            if "plan" in node_output and node_output["plan"]:
                plan_preview = node_output["plan"][:150].replace("\n", " ")
                print(f"  📝 plan 已更新: {plan_preview}...")

            if "test_output" in node_output and node_output["test_output"]:
                # 只打印关键行（PASS/FAIL/ERROR）
                key_lines = [l for l in node_output["test_output"].splitlines()
                             if any(kw in l.upper() for kw in ["PASS", "FAIL", "ERROR", "EXIT", "OK"])]
                summary = " | ".join(key_lines[:3]) if key_lines else node_output["test_output"][:80]
                print(f"  🧪 test_output: {summary}")

            if "review_result" in node_output and node_output["review_result"]:
                print(f"  🏷️  review_result: {node_output['review_result'][:100]}")

            if "review_retries" in node_output:
                print(f"  🔁 review_retries: {node_output['review_retries']}")

            # 打印消息内容预览
            if "messages" in node_output:
                for msg in node_output["messages"]:
                    role = type(msg).__name__
                    content_preview = _preview_content(msg)
                    print(f"  消息类型: {role}")
                    print(f"  内容预览: {content_preview}")

                    # 保存 Reviewer 最终通过或 Coder 完成报告作为输出
                    if role == "AIMessage" and not getattr(msg, "tool_calls", None):
                        final_output = msg.content

    print_separator("═")
    print(f"\n🎉 流水线运行完毕！共执行 {step_count} 步")
    print(f"   流程: Planner → Coder ⇄ Tools → TestRunner → Reviewer\n")

    if final_output:
        print("📝 最终输出报告：")
        print_separator("─")
        print(final_output)
        print_separator("─")


def _preview_content(msg) -> str:
    """
    提取消息内容的简短预览，避免日志过长。

    Args:
        msg: LangChain 消息对象

    Returns:
        截断后的内容预览字符串
    """
    MAX_PREVIEW = 120

    # 处理带有 tool_calls 的 AI 消息
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        calls_info = ", ".join(
            f"{tc['name']}({list(tc.get('args', {}).keys())})"
            for tc in msg.tool_calls
        )
        return f"[工具调用] → {calls_info}"

    # 处理普通文本内容
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        if len(content) > MAX_PREVIEW:
            return content[:MAX_PREVIEW] + "..."
        return content or "(空)"

    return str(content)[:MAX_PREVIEW]


# ══════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════
if __name__ == "__main__":
    try:
        run_agent(TEST_ISSUE)
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断运行")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Agent 运行出错: {type(e).__name__}: {e}")
        raise
