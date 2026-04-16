"""
tests/conftest.py
-----------------
共享 pytest fixtures。
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.workspace import set_workspace, reset_workspace


@pytest.fixture()
def tmp_workspace(tmp_path):
    """创建临时工作目录并设置为当前 workspace，测试结束后自动还原。"""
    token = set_workspace(str(tmp_path))
    yield tmp_path
    reset_workspace(token)


@pytest.fixture()
def sample_repo(tmp_path):
    """创建一个包含简单 Python 文件的 git 仓库作为测试工作目录。"""
    # 创建样本文件
    (tmp_path / "calc.py").write_text("def add(a, b): return a + b\n")
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import add\ndef test_add(): assert add(1, 2) == 3\n"
    )

    # 初始化 git 仓库
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--allow-empty"],
        cwd=tmp_path,
        capture_output=True,
        env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    token = set_workspace(str(tmp_path))
    yield tmp_path
    reset_workspace(token)
