# AutoPatch Development Issues

---

## Issue #001: write_and_replace_file 导致大文件截断

**日期**: 2026-04-12
**状态**: 已修复
**发现场景**: SWE-bench 评测 `sympy__sympy-20154`

### 现象

- Coder 对 `sympy/utilities/iterables.py`（78KB, 2000+ 行）使用 `write_and_replace_file` 修改 `partitions()` 函数
- LLM 输出截断，文件从 78022 字符缩减到 50627 字符，后半部分函数全部丢失
- 导致 `ImportError: cannot import name 'has_dups'`，所有测试失败
- 同时 Coder 错误地重写了测试文件（31194→3675 字符），删除了大量测试
- Reviewer 打回 3 次后强制结束，最终 resolve rate 0%

### 根因

`write_and_replace_file` 要求 LLM 输出完整文件内容，大文件场景下 LLM output 必然截断。工具设计不适合编辑大文件。

### 修复方案

1. **新增 `edit_file` 工具** — 基于 old_string → new_string 的精确替换，只传修改片段，不需要输出整个文件
2. **更新 Coder system prompt** — 引导 Coder 优先使用 `edit_file` 进行局部修改，仅在创建新文件时使用 `write_and_replace_file`
3. **增加 Coder prompt 约束** — 禁止修改测试文件，只允许修改源码

### 修复内容

1. **`tools/file_tools.py`** — 新增 `edit_file(file_path, old_string, new_string)` 工具，基于精确文本匹配做局部替换
2. **`tools/__init__.py`** — 导出 `edit_file`
3. **`agent/graph.py`** — 注册 `edit_file` 到 TOOLS 列表 + 更新 Coder system prompt：
   - 强制要求修改已有文件时必须使用 `edit_file`
   - `write_and_replace_file` 仅限创建新文件
   - 禁止修改 tests/ 目录下的测试文件

---

## Issue #002: Reviewer PASS 判定被 Markdown 代码块干扰

**日期**: 2026-04-12
**状态**: 已修复
**发现场景**: SWE-bench 评测 `sympy__sympy-20154` (fix1 run)

### 现象

Reviewer 输出 `` ```\nPASS\n理由：...``` `` 被代码块包裹，`conclusion.upper().startswith("PASS")` 判定失败，PASS 被误判为 REJECT，导致不必要的打回重做。

### 修复内容

`agent/graph.py` `reviewer_node` 中提取结论后先剥离 ``` 围栏再判断 PASS/REJECT。

---

## Issue #003: eval 工作区缺少 pytest

**日期**: 2026-04-12
**状态**: 已修复
**发现场景**: SWE-bench 评测 `sympy__sympy-20154`

### 现象

`instance_env.py` 只执行 `pip install -e .` 安装目标 repo，未安装 pytest。Agent 的 TestRunner 和 eval 的 verify.py 均调用 pytest 运行测试，导致所有测试 exit code 1。

### 修复内容

`eval/instance_env.py` `_install_deps()` 开头增加 `pip install pytest`。

---

## Issue #004: Coder 仍然修改测试文件

**日期**: 2026-04-12
**状态**: 已修复
**发现场景**: SWE-bench 评测 `sympy__sympy-20154` (fix1 run)

### 现象

尽管 Coder prompt 中明确写了"禁止修改 tests/ 目录"，Coder 仍修改了 `test_iterables.py`（移除 `.copy()` 调用）。纯 prompt 约束对 LLM 不够可靠。

### 修复内容

`tools/file_tools.py` 中 `edit_file` 和 `write_and_replace_file` 增加工具级拦截：通过正则匹配 `tests/`、`test/`、`test_*.py` 等路径模式，直接拒绝写入测试文件并返回提示信息。
