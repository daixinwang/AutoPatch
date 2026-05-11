# Codebase Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete dead files (`calc.py`, `main.py`) and move five library modules into a `core/` package so the root directory contains only entry-point scripts.

**Architecture:** Each library module is moved with `git mv` to preserve git history, then all consumers are updated. Moves happen one module at a time with a test run after each, so the repo is always in a working state.

**Tech Stack:** Python, pytest

---

## File Map

| Action | Path |
|--------|------|
| Delete | `calc.py` |
| Delete | `main.py` |
| Create | `core/__init__.py` |
| Move | `config.py` → `core/config.py` |
| Move | `logging_config.py` → `core/logging_config.py` |
| Move | `diff_generator.py` → `core/diff_generator.py` |
| Move | `github_client.py` → `core/github_client.py` |
| Move | `task_store.py` → `core/task_store.py` |
| Modify | `agent/graph.py` |
| Modify | `autopatch.py` |
| Modify | `server.py` |
| Modify | `eval/evaluator.py` |
| Modify | `tests/test_github_client.py` |
| Modify | `tests/test_task_store.py` |

---

## Task 1: Establish baseline and delete dead files

**Files:**
- Delete: `calc.py`
- Delete: `main.py`

- [ ] **Step 1: Run the full test suite to establish a passing baseline**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass. If any fail, stop and investigate before continuing.

- [ ] **Step 2: Delete dead files**

```bash
git rm calc.py main.py
```

Expected output:
```
rm 'calc.py'
rm 'main.py'
```

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
python -m pytest tests/ -q
```

Expected: same pass count as Step 1, no failures.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete dead files calc.py and main.py"
```

---

## Task 2: Create `core/` package and move `config.py`

**Files:**
- Create: `core/__init__.py`
- Move: `config.py` → `core/config.py`
- Modify: `agent/graph.py` (line 49)
- Modify: `server.py` (line 68)
- Modify: `github_client.py` (line 34) — temporary, until Task 5 moves it

- [ ] **Step 1: Create the `core/` package**

```bash
mkdir core
touch core/__init__.py
git add core/__init__.py
```

- [ ] **Step 2: Move `config.py` into `core/`**

```bash
git mv config.py core/config.py
```

- [ ] **Step 3: Update `agent/graph.py` — change `from config import` to `from core.config import`**

In `agent/graph.py`, replace lines 49–56:

```python
# Before
from config import (
    MAX_CODER_STEPS,
    MAX_MESSAGE_CHARS,
    MAX_REVIEW_RETRIES,
    MAX_REVIEWER_TOOL_CALLS,
    OPENAI_MODEL_NAME,
    RECURSION_LIMIT,
)
```

```python
# After
from core.config import (
    MAX_CODER_STEPS,
    MAX_MESSAGE_CHARS,
    MAX_REVIEW_RETRIES,
    MAX_REVIEWER_TOOL_CALLS,
    OPENAI_MODEL_NAME,
    RECURSION_LIMIT,
)
```

- [ ] **Step 4: Update `server.py` — change `from config import`**

In `server.py`, find line 68:

```python
# Before
from config import MAX_CONCURRENT_PATCHES as _CFG_MAX_CONCURRENT, DB_POOL_MAX_SIZE, RECURSION_LIMIT
```

```python
# After
from core.config import MAX_CONCURRENT_PATCHES as _CFG_MAX_CONCURRENT, DB_POOL_MAX_SIZE, RECURSION_LIMIT
```

- [ ] **Step 5: Update `github_client.py` — change `from config import` (temporary fix until Task 5)**

In `github_client.py`, find line 34:

```python
# Before
from config import GITHUB_RETRY_BACKOFF_BASE, GITHUB_RETRY_MAX_ATTEMPTS
```

```python
# After
from core.config import GITHUB_RETRY_BACKOFF_BASE, GITHUB_RETRY_MAX_ATTEMPTS
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add -u
git commit -m "refactor: move config.py into core/ package"
```

---

## Task 3: Move `logging_config.py` to `core/`

**Files:**
- Move: `logging_config.py` → `core/logging_config.py`
- Modify: `autopatch.py` (line 43)
- Modify: `server.py` (line 60)

- [ ] **Step 1: Move the file**

```bash
git mv logging_config.py core/logging_config.py
```

- [ ] **Step 2: Update `autopatch.py`**

Find line 43:

```python
# Before
from logging_config import setup_logging
```

```python
# After
from core.logging_config import setup_logging
```

- [ ] **Step 3: Update `server.py`**

Find line 60:

```python
# Before
from logging_config import setup_logging
```

```python
# After
from core.logging_config import setup_logging
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "refactor: move logging_config.py into core/"
```

---

## Task 4: Move `diff_generator.py` to `core/`

**Files:**
- Move: `diff_generator.py` → `core/diff_generator.py`
- Modify: `autopatch.py` (lines 52–57)
- Modify: `server.py` (line 63)
- Modify: `eval/evaluator.py` (line 100)

- [ ] **Step 1: Move the file**

```bash
git mv diff_generator.py core/diff_generator.py
```

- [ ] **Step 2: Update `autopatch.py`**

Find lines 52–57:

```python
# Before
from diff_generator import (
    generate_diff,
    get_changed_files,
    print_diff_summary,
    write_diff_file,
)
```

```python
# After
from core.diff_generator import (
    generate_diff,
    get_changed_files,
    print_diff_summary,
    write_diff_file,
)
```

- [ ] **Step 3: Update `server.py`**

Find line 63:

```python
# Before
from diff_generator import generate_diff, get_changed_files, write_diff_file
```

```python
# After
from core.diff_generator import generate_diff, get_changed_files, write_diff_file
```

- [ ] **Step 4: Update `eval/evaluator.py`**

Find line 100 (inside a function body):

```python
# Before
            from diff_generator import generate_diff
```

```python
# After
            from core.diff_generator import generate_diff
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "refactor: move diff_generator.py into core/"
```

---

## Task 5: Move `github_client.py` to `core/`

**Files:**
- Move: `github_client.py` → `core/github_client.py`
- Modify: `core/github_client.py` (line 34 — make import relative)
- Modify: `autopatch.py` (line 51)
- Modify: `server.py` (line 62)
- Modify: `tests/test_github_client.py` (line 10)

- [ ] **Step 1: Move the file**

```bash
git mv github_client.py core/github_client.py
```

- [ ] **Step 2: Update internal import inside `core/github_client.py`**

Find line 34 (now in `core/github_client.py`):

```python
# Before
from core.config import GITHUB_RETRY_BACKOFF_BASE, GITHUB_RETRY_MAX_ATTEMPTS
```

```python
# After — use relative import since both files are now in core/
from .config import GITHUB_RETRY_BACKOFF_BASE, GITHUB_RETRY_MAX_ATTEMPTS
```

- [ ] **Step 3: Update `autopatch.py`**

Find line 51:

```python
# Before
from github_client import GitHubClient, RepoWorkspace, parse_github_url
```

```python
# After
from core.github_client import GitHubClient, RepoWorkspace, parse_github_url
```

- [ ] **Step 4: Update `server.py`**

Find line 62:

```python
# Before
from github_client import GitHubClient, RepoWorkspace, parse_github_url
```

```python
# After
from core.github_client import GitHubClient, RepoWorkspace, parse_github_url
```

- [ ] **Step 5: Update `tests/test_github_client.py`**

Find line 10:

```python
# Before
from github_client import GitHubIssue, RepoInfo, parse_github_url
```

```python
# After
from core.github_client import GitHubIssue, RepoInfo, parse_github_url
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add -u
git commit -m "refactor: move github_client.py into core/"
```

---

## Task 6: Move `task_store.py` to `core/`

**Files:**
- Move: `task_store.py` → `core/task_store.py`
- Modify: `server.py` (line 67)
- Modify: `tests/test_task_store.py` (line 14)

- [ ] **Step 1: Move the file**

```bash
git mv task_store.py core/task_store.py
```

- [ ] **Step 2: Update `server.py`**

Find line 67:

```python
# Before
from task_store import TaskStore
```

```python
# After
from core.task_store import TaskStore
```

- [ ] **Step 3: Update `tests/test_task_store.py`**

Find line 14:

```python
# Before
from task_store import TaskStore
```

```python
# After
from core.task_store import TaskStore
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass with the same count as Task 1 Step 1.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "refactor: move task_store.py into core/"
```

---

## Final Verification

- [ ] **Confirm root directory is clean**

```bash
ls *.py
```

Expected output (only entry points remain):
```
autopatch.py  run_eval.py  server.py
```

- [ ] **Confirm `core/` contains all moved modules**

```bash
ls core/
```

Expected:
```
__init__.py  config.py  diff_generator.py  github_client.py  logging_config.py  task_store.py
```

- [ ] **Run full suite one final time**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass, no import errors.
