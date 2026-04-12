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

---

## Issue #005: Coder 被拦截后陷入无限搜索循环

**日期**: 2026-04-12
**状态**: 已修复
**发现场景**: SWE-bench 评测 `sympy__sympy-20154` (fix3 run)

### 现象

- Coder 被 Reviewer 打回后，试图创建/修改测试文件 → 被工具级拦截拒绝
- Coder 不知如何应对拒绝，开始逐个搜索测试函数名（`test_partitions`, `test_uniq`, `test_rotate`...），从 Step 35 到 Step 99 执行了 60+ 次无意义的 `search_codebase`
- 最终撞上 `recursion_limit=100`，触发 `GraphRecursionError`，status=error

### 根因

Coder prompt 没有指导"被拦截后应该怎么做"。LLM 在工具调用被拒绝后缺乏恢复策略，陷入重复搜索的死循环。

### 修复方案

1. **Coder prompt 增加拒绝恢复指引** — 明确告知：如果工具返回拒绝信息，不要重试也不要创建新测试文件，专注于让源码修改通过现有测试
2. **拦截消息增加行动建议** — 工具拒绝时不仅说"不允许"，还提示"请调整源码修改使其通过现有测试，确保修复兼容现有行为模式"

### 修复内容

- `tools/file_tools.py`: 拒绝消息增加具体行动指引
- `agent/graph.py`: Coder prompt 增加"不要重试被拒绝的操作"指引

---

## Issue #006: edit_file 多处匹配时 Coder 只改了一处

**日期**: 2026-04-12
**状态**: 已修复
**发现场景**: SWE-bench 评测 `sympy__sympy-20154` (fix3 run)

### 现象

- `partitions()` 函数有两个 `yield ms` 语句（初始 yield + while 循环内的 yield）
- Coder 调用 `edit_file` 用 `"yield ms"` → `"yield ms.copy()"` 替换，工具返回"出现 2 次，仅替换第一处"的警告
- Coder 忽略了这个警告，没有对第二处 yield 做修改 → 修复不完整 → 测试失败
- 打回后 Coder 反复撤销/重做同一处修改，始终没有处理第二处

### 根因

1. edit_file 的多处匹配警告不够强烈，LLM 容易忽略
2. Coder prompt 没有强调：遇到多处匹配警告时，需要提供更长的上下文来唯一定位每一处修改

### 修复方案

1. **edit_file 多处匹配时改为报错（不执行替换）** — 强制 Coder 提供更多上下文使 old_string 唯一匹配
2. **Coder prompt 增加 edit_file 使用指导** — 强调 old_string 必须唯一匹配，遇到多处匹配需提供更多上下文行

### 修复内容

- `tools/file_tools.py`: 多处匹配从"警告但继续执行"改为"报错并拒绝执行"，错误消息明确指导如何提供唯一上下文
- `agent/graph.py`: Coder prompt 增加 old_string 唯一性要求和多处修改策略说明
