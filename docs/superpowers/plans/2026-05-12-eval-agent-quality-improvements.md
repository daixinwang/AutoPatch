# Eval & Agent Quality Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复三个经评测验证的缺陷：Reviewer 误判 PASS、Coder 引入循环 import、eval diff 包含 test_patch 内容。

**Architecture:** 按 C→B→A 顺序：先改 Reviewer 提示词（零风险），再给 Coder 加 import 验证工具，最后修复 eval 框架的 diff 污染。

**Tech Stack:** Python, LangGraph, pytest, subprocess, re

---

## 文件改动一览

| 文件 | 操作 | 原因 |
|---|---|---|
| `agent/graph.py` | 修改 `REVIEWER_SYSTEM_PROMPT` | Task 1：强制 Reviewer 以 TestRunner 为权威 |
| `tools/execute_tools.py` | 新增 `verify_importable` 工具 | Task 2：让 Coder 能验证 import |
| `agent/graph.py` | 修改 `TOOLS` + `CODER_SYSTEM_PROMPT` | Task 2：注册工具 + 指导 Coder 使用 |
| `tests/test_execute_tools.py` | 新建 | Task 2：工具单元测试 |
| `core/diff_generator.py` | 新增 `filter_diff` 函数 | Task 3：过滤 test_patch 文件 |
| `eval/instance_env.py` | 记录 `test_patch_files` | Task 3：提供需过滤的文件集合 |
| `eval/evaluator.py` | 调用 `filter_diff` | Task 3：应用过滤到 agent_patch |
| `tests/test_diff_filter.py` | 新建 | Task 3：`filter_diff` 单元测试 |

---

## Task 1：强制 Reviewer 以 TestRunner 为权威

**Files:**
- Modify: `agent/graph.py`（`REVIEWER_SYSTEM_PROMPT`）

- [ ] **Step 1：找到 REVIEWER_SYSTEM_PROMPT 中的评审步骤区域**

在 `agent/graph.py` 中找到 `REVIEWER_SYSTEM_PROMPT`，定位到 `## 评审标准` 一节（当前第一条是"（最优先）Coder 是否修改了测试文件"）。

- [ ] **Step 2：在评审标准第一条之后插入两条强制规则**

将 `## 评审标准` 的前两条替换为如下内容（保留其余条目不变）：

```
## 评审标准
- [ ] **（最优先）Coder 是否修改了测试文件？** 若消息历史中出现对 tests/ 下文件或 test_*.py / *_test.py 的写操作，**立即 REJECT**，原因写明"不允许修改测试文件"
- [ ] **（强制）TestRunner 报告任意测试失败 → 必须 REJECT**：若 TestRunner 输出中包含 FAILED / ERROR / exit 非 0，无论静态检查结论如何，必须输出 REJECT，并在原因中引用具体失败的测试名称。禁止用"代码逻辑看起来正确"来覆盖测试失败结论。
- [ ] **（强制）PASS_TO_PASS 测试全部缺失 → 必须 REJECT**：若 TestRunner 输出中完全没有任何 PASSED 记录，且项目存在测试文件，视为模块导入崩溃，必须 REJECT，原因写"疑似模块导入失败：TestRunner 输出无任何 PASSED 记录，请用 verify_importable 验证修改的文件"。
```

- [ ] **Step 3：提交**

```bash
git add agent/graph.py
git commit -m "fix: enforce TestRunner authority in Reviewer prompt"
```

---

## Task 2：新增 verify_importable 工具

**Files:**
- Modify: `tools/execute_tools.py`
- Modify: `agent/graph.py`（`TOOLS` 列表 + `CODER_SYSTEM_PROMPT`）
- Create: `tests/test_execute_tools.py`

- [ ] **Step 1：写失败测试**

新建 `tests/test_execute_tools.py`：

```python
"""
tests/test_execute_tools.py
---------------------------
Tests for tools/execute_tools.py (verify_importable).
"""
import sys
import textwrap

import pytest

from tools.execute_tools import verify_importable


class TestVerifyImportable:
    """verify_importable tool tests."""

    def test_valid_module(self, tmp_workspace):
        # 写一个合法的 Python 模块
        (tmp_workspace / "mymod.py").write_text("x = 1\n", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "mymod.py"})
        assert "成功" in result
        assert "mymod" in result

    def test_syntax_error(self, tmp_workspace):
        (tmp_workspace / "broken.py").write_text("def foo(\n", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "broken.py"})
        assert "失败" in result or "错误" in result

    def test_import_error(self, tmp_workspace):
        # 导入一个不存在的依赖
        (tmp_workspace / "bad_import.py").write_text(
            "import nonexistent_pkg_xyz\n", encoding="utf-8"
        )
        result = verify_importable.invoke({"file_path": "bad_import.py"})
        assert "失败" in result or "错误" in result

    def test_file_not_found(self, tmp_workspace):
        result = verify_importable.invoke({"file_path": "no_such_file.py"})
        assert "错误" in result or "不存在" in result

    def test_non_py_file(self, tmp_workspace):
        (tmp_workspace / "readme.txt").write_text("hello", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "readme.txt"})
        assert "错误" in result

    def test_nested_module(self, tmp_workspace):
        # 嵌套包模块
        pkg = tmp_workspace / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "utils.py").write_text("def helper(): return 42\n", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "mypkg/utils.py"})
        assert "成功" in result
        assert "mypkg.utils" in result
```

- [ ] **Step 2：运行测试，确认失败（工具尚未实现）**

```bash
source .venv/bin/activate
pytest tests/test_execute_tools.py -v
```

期望：`AttributeError: module 'tools.execute_tools' has no attribute 'verify_importable'`

- [ ] **Step 3：在 `tools/execute_tools.py` 末尾添加 `verify_importable` 工具**

在文件末尾追加：

```python
# ──────────────────────────────────────────────
# 工具 4：验证 Python 模块是否可正常 import
# ──────────────────────────────────────────────
@tool
def verify_importable(file_path: str) -> str:
    """
    验证修改后的 Python 源文件是否可以正常 import（检测语法错误和循环依赖）。

    在修改任何 Python 源文件后调用此工具，确保没有破坏模块的可导入性。

    Args:
        file_path: 要验证的 Python 文件路径（相对于工作目录，如 "sympy/printing/ccode.py"）

    Returns:
        成功时返回 "[成功] 模块可正常导入：<module_name>"；
        失败时返回包含完整错误信息的字符串。
    """
    logger.debug(f"  [Tool: verify_importable] 验证文件: {file_path}")
    try:
        path = resolve_workspace_path(file_path)

        if not path.exists():
            return f"[错误] 文件不存在: {file_path}"
        if path.suffix.lower() != ".py":
            return f"[错误] 只支持 .py 文件，收到: {file_path}"

        # 将相对路径转换为模块名
        # 例：sympy/printing/ccode.py → sympy.printing.ccode
        rel = Path(file_path).as_posix().removesuffix(".py")
        module_name = rel.replace("/", ".")

        cwd = get_workspace()
        result = _run_subprocess(
            [sys.executable, "-c", f"import {module_name}"],
            cwd=cwd,
            timeout=15,
        )

        if result["timed_out"]:
            return (
                f"[超时] import {module_name} 超时（15s），"
                "可能存在循环导入，请检查模块级 import 语句"
            )

        if result["returncode"] == 0:
            logger.info(f"  [Tool: verify_importable] ✅ 可正常导入: {module_name}")
            return f"[成功] 模块可正常导入：{module_name}"

        error_output = _truncate_output(result["stderr"] or result["stdout"])
        logger.warning(f"  [Tool: verify_importable] ❌ 导入失败: {module_name}")
        return (
            f"[失败] import {module_name} 出错，请修复后重试：\n{error_output}"
        )

    except Exception as e:
        error_msg = f"[错误] verify_importable 执行失败: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: verify_importable] {error_msg}")
        return error_msg
```

同时在文件顶部导入区补充 `get_workspace`（与已有的 `resolve_workspace_path` 同一行或紧邻）：

```python
from tools.workspace import resolve_workspace_path, get_workspace
```

- [ ] **Step 4：运行测试，确认通过**

```bash
pytest tests/test_execute_tools.py -v
```

期望：6 个测试全部 PASSED

- [ ] **Step 5：将 `verify_importable` 加入 Coder 工具集，并更新提示词**

在 `agent/graph.py` 中：

**(a)** 更新导入：

```python
from tools.execute_tools import run_pytest, run_python_script, run_test_command, verify_importable
```

**(b)** 将 `verify_importable` 加入 `TOOLS` 列表（Coder 全量工具集）：

```python
TOOLS = [
    # ── 文件读写 ──────────────────────────
    read_file,
    edit_file,
    write_and_replace_file,
    # ── 代码库检索 ────────────────────────
    list_directory,
    search_codebase,
    find_definition,
    grep_in_file,
    # ── Import 验证 ───────────────────────
    verify_importable,
]
```

**(c)** 在 `CODER_SYSTEM_PROMPT` 的 `## ⚠️ 重要规则` 一节末尾追加新规则：

```
### 修改源码后必须验证 import
- 每次修改 .py 源文件（非测试文件）后，**必须**立即调用 `verify_importable("<文件路径>")` 验证模块可正常导入。
- 若返回 `[失败]` 或 `[超时]`，必须先修复 import 错误再继续其他步骤。
- 常见错误：将 `from xxx import yyy` 从函数内部挪到模块顶层可能引发循环导入；若不确定，保留在函数内部。
```

- [ ] **Step 6：提交**

```bash
git add tools/execute_tools.py agent/graph.py tests/test_execute_tools.py
git commit -m "feat: add verify_importable tool and require Coder to validate imports"
```

---

## Task 3：修复 eval diff 污染

**Files:**
- Modify: `core/diff_generator.py`（新增 `filter_diff`）
- Modify: `eval/instance_env.py`（记录 `test_patch_files`）
- Modify: `eval/evaluator.py`（调用 `filter_diff`）
- Create: `tests/test_diff_filter.py`

- [ ] **Step 1：写 `filter_diff` 的失败测试**

新建 `tests/test_diff_filter.py`：

```python
"""
tests/test_diff_filter.py
-------------------------
Tests for core/diff_generator.filter_diff.
"""
from core.diff_generator import filter_diff

SAMPLE_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc..def 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,3 @@
 x = 1
+y = 2
 z = 3
diff --git a/tests/test_foo.py b/tests/test_foo.py
index 111..222 100644
--- a/tests/test_foo.py
+++ b/tests/test_foo.py
@@ -1 +1,3 @@
 def test_x(): pass
+def test_y(): pass
diff --git a/src/bar.py b/src/bar.py
index 333..444 100644
--- a/src/bar.py
+++ b/src/bar.py
@@ -1 +1,2 @@
 a = 1
+b = 2
"""


def test_filter_excludes_specified_file():
    result = filter_diff(SAMPLE_DIFF, {"tests/test_foo.py"})
    assert "tests/test_foo.py" not in result
    assert "src/foo.py" in result
    assert "src/bar.py" in result


def test_filter_empty_exclude_set_returns_original():
    result = filter_diff(SAMPLE_DIFF, set())
    assert result == SAMPLE_DIFF


def test_filter_empty_diff_returns_empty():
    assert filter_diff("", {"tests/test_foo.py"}) == ""


def test_filter_exclude_all_files():
    result = filter_diff(
        SAMPLE_DIFF,
        {"src/foo.py", "tests/test_foo.py", "src/bar.py"},
    )
    assert result.strip() == ""


def test_filter_preserves_unrelated_blocks():
    result = filter_diff(SAMPLE_DIFF, {"src/foo.py"})
    assert "src/bar.py" in result
    assert "tests/test_foo.py" in result
    assert "src/foo.py" not in result
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest tests/test_diff_filter.py -v
```

期望：`ImportError: cannot import name 'filter_diff' from 'core.diff_generator'`

- [ ] **Step 3：在 `core/diff_generator.py` 末尾添加 `filter_diff` 函数**

在文件末尾 `print_diff_summary` 函数之后追加：

```python
def filter_diff(diff: str, exclude_paths: set) -> str:
    """
    从 unified diff 字符串中过滤掉指定文件的 diff 块。

    用于从 agent_patch 中剔除由评测框架（test_patch）引入的测试文件改动，
    确保 agent_patch 只包含 Agent 实际修改的内容。

    Args:
        diff:          unified diff 字符串（git diff HEAD 的输出）
        exclude_paths: 需要排除的文件路径集合（相对于仓库根目录，如 "tests/test_foo.py"）

    Returns:
        过滤后的 diff 字符串；若无剩余块则返回空字符串
    """
    if not diff or not exclude_paths:
        return diff

    import re as _re
    blocks = _re.split(r"(?=^diff --git )", diff, flags=_re.MULTILINE)
    result = []
    for block in blocks:
        if not block.strip():
            continue
        m = _re.match(r"^diff --git a/(.+?) b/", block)
        if m and m.group(1) in exclude_paths:
            continue
        result.append(block)
    return "".join(result)
```

- [ ] **Step 4：运行测试，确认通过**

```bash
pytest tests/test_diff_filter.py -v
```

期望：5 个测试全部 PASSED

- [ ] **Step 5：在 `eval/instance_env.py` 记录 test_patch 修改的文件**

**(a)** 在 `InstanceEnvironment.__init__` 中新增属性：

```python
def __init__(self, instance: SWEBenchInstance, config: EvalConfig):
    self.instance = instance
    self.config = config
    self.workspace: Optional[Path] = None
    self._worktree_created = False
    self.test_patch_files: set = set()   # ← 新增：test_patch 修改的文件路径集合
```

**(b)** 修改 `setup()` 方法中 apply test_patch 的调用，应用后立即记录变更文件：

将：
```python
        # 3. apply test_patch
        if self.instance.test_patch:
            self._apply_patch(workspace, self.instance.test_patch, label="test_patch")
```

替换为：
```python
        # 3. apply test_patch，并记录被修改的文件（用于后续 diff 过滤）
        if self.instance.test_patch:
            self._apply_patch(workspace, self.instance.test_patch, label="test_patch")
            self.test_patch_files = self._get_changed_files(workspace)
```

**(c)** 在 `InstanceEnvironment` 末尾（`cleanup` 方法之后）新增辅助方法：

```python
    def _get_changed_files(self, workspace: Path) -> set:
        """返回工作区相对于 HEAD 的已修改文件路径集合。"""
        result = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        return {
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        }
```

- [ ] **Step 6：在 `eval/evaluator.py` 中调用 `filter_diff`**

**(a)** 更新导入：

```python
from core.diff_generator import generate_diff, filter_diff
```

**(b)** 将 Step 4（获取 diff）的代码替换为：

将：
```python
            # 4. 获取 Agent 生成的 diff
            from core.diff_generator import generate_diff
            result.agent_patch = generate_diff(workspace_str)
```

替换为：
```python
            # 4. 获取 Agent 生成的 diff，过滤掉 test_patch 引入的文件
            raw_diff = generate_diff(workspace_str)
            result.agent_patch = filter_diff(raw_diff, env.test_patch_files)
```

- [ ] **Step 7：运行全部测试，确认无回归**

```bash
pytest tests/ -v
```

期望：全部 PASSED

- [ ] **Step 8：提交**

```bash
git add core/diff_generator.py eval/instance_env.py eval/evaluator.py tests/test_diff_filter.py
git commit -m "fix: exclude test_patch files from agent_patch in eval diff"
```

---

## 验收

全部任务完成后，重跑一次评测确认改进生效：

```bash
python run_eval.py --max-instances 1 --repos sympy/sympy --no-resume
```

观察：
- Reviewer 是否在 TestRunner 失败时输出 REJECT（不再误判 PASS）
- Coder 是否在修改源文件后自动调用 `verify_importable`
- `eval/results/<run_id>/patches/` 中的 diff 是否不再包含测试文件改动
