# 评测与 Agent 质量改进设计

Date: 2026-05-12
Status: Approved

## 背景

三次 SWE-bench 评测暴露了三个独立问题：

1. **agent_patch 包含 test_patch 内容**：评测框架在运行 Agent 前通过 `git apply` 写入
   `test_patch`，导致 `generate_diff`（`git diff HEAD`）将测试文件改动混入 agent_patch，
   污染评测数据。

2. **Coder 将 import 挪至模块级导致循环依赖**：gpt-5.4 的 `_print_sinc` 实现方向正确，
   但把 `from sympy.functions import Piecewise, sin` 提至模块顶部，触发 sympy 内部循环
   导入，导致所有 PASS_TO_PASS 测试全崩。

3. **Reviewer 无视 TestRunner 输出误判 PASS**：Reviewer 静态阅读测试文件后认为实现正确，
   忽视 TestRunner 报告的失败，输出错误的 PASS 结论。

---

## 方案 A：修复 eval diff 污染

### 目标
agent_patch 只反映 Agent 实际修改的内容，不包含 test_patch 带来的测试文件变动。

### 设计
- `InstanceEnvironment.setup()` 在 `_apply_patch(test_patch)` 之后，记录被修改的文件路径
  集合，作为 `test_patch_files: set[str]` 属性保存。
- `InstanceEvaluator.evaluate()` 在调用 `generate_diff` 后，过滤掉 `test_patch_files`
  中的文件对应的 diff 块。
- 过滤逻辑封装为 `core/diff_generator.py` 的新函数 `filter_diff(diff: str, exclude_paths: set[str]) -> str`。

### 影响范围
`eval/instance_env.py`、`eval/evaluator.py`、`core/diff_generator.py`

---

## 方案 B：给 Coder 添加 import 验证工具

### 目标
Coder 在修改源文件后能立即验证模块是否可正常导入，避免循环 import 问题浪费多轮重试。

### 设计
- 在 `tools/execute_tools.py` 新增工具 `verify_importable(module_path: str) -> str`：
  - 接收 Python 文件路径（如 `sympy/printing/ccode.py`）
  - 将路径转换为模块名（替换路径分隔符、去掉 `.py`）
  - 执行 `python -c "import <module_name>"` 并返回成功或详细错误
  - 超时 15 秒，捕获 ImportError / SyntaxError 等
- 加入 `TOOLS` 列表（Coder 全量工具集）
- 在 `CODER_SYSTEM_PROMPT` 中新增规则："修改源码文件后，**必须**调用
  `verify_importable` 验证模块可以正常 import，若报错须修复后再继续"

### 影响范围
`tools/execute_tools.py`、`agent/graph.py`（TOOLS 列表 + Coder 提示词）

---

## 方案 C：强制 Reviewer 以 TestRunner 为权威

### 目标
Reviewer 不得用静态代码分析覆盖 TestRunner 报告的失败，防止误判 PASS。

### 设计
在 `REVIEWER_SYSTEM_PROMPT` 中新增两条强制规则（优先级高于其他标准）：

1. **TestRunner 失败 → 必须 REJECT**：若 TestRunner 报告任意测试失败，无论静态检查
   结论如何，必须输出 REJECT，并在原因中明确引用失败的测试名称。

2. **全量 PASS_TO_PASS 缺失 → 必须 REJECT**：若 TestRunner 输出中完全没有 PASS_TO_PASS
   测试的通过记录（通常意味着模块导入崩溃），视为严重回归，必须 REJECT，原因写
   "疑似模块导入失败，需要验证"。

### 影响范围
`agent/graph.py`（`REVIEWER_SYSTEM_PROMPT`）

---

## 实现顺序

C → B → A

- C 改提示词，零风险，效果立竿见影
- B 新增工具，需要同步更新工具列表和提示词
- A 改评测框架，涉及三个文件，最后实现
