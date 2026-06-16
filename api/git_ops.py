"""
api/git_ops.py
--------------
Git operations used by the apply endpoint.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def git_apply_and_push(
    repo_path,
    branch: str,
    diff_content: str,
    repo_info,
    token: str,
) -> None:
    """
    Apply a unified diff, commit it on a new branch, and push that branch.

    This is a synchronous function intended to run inside an asyncio executor.

    Args:
        repo_path: Local git repository path.
        branch: New branch name, such as "autopatch/issue-42".
        diff_content: Unified diff content.
        repo_info: RepoInfo with owner and repo attributes.
        token: GitHub token with write permissions.

    Raises:
        subprocess.CalledProcessError: Any git command failure.
    """
    cwd = str(repo_path)

    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=cwd, check=True, capture_output=True, text=True,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".diff", delete=False, encoding="utf-8"
    ) as f:
        f.write(diff_content)
        diff_file = f.name

    try:
        subprocess.run(
            ["git", "apply", "--whitespace=fix", diff_file],
            cwd=cwd, check=True, capture_output=True, text=True,
        )
    finally:
        Path(diff_file).unlink(missing_ok=True)

    subprocess.run(
        ["git", "config", "user.email", "autopatch@bot.local"],
        cwd=cwd, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AutoPatch"],
        cwd=cwd, check=True, capture_output=True,
    )

    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: AutoPatch generated patch"],
        cwd=cwd, check=True, capture_output=True, text=True,
    )

    remote_url = (
        f"https://x-access-token:{token}@github.com/"
        f"{repo_info.owner}/{repo_info.repo}.git"
    )
    git_push_cmd = ["git", "-c", "credential.helper=", "push", remote_url, branch]
    result = subprocess.run(
        git_push_cmd,
        cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode != 0:
        if "already exists" in result.stderr:
            from datetime import datetime
            branch_retry = f"{branch}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            subprocess.run(
                ["git", "branch", "-m", branch, branch_retry],
                cwd=cwd, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-c", "credential.helper=", "push", remote_url, branch_retry],
                cwd=cwd, check=True, capture_output=True, text=True,
            )
            logger.info("[apply] 分支已存在，重命名为 %s 后成功 push", branch_retry)
        else:
            safe_stderr = result.stderr.replace(remote_url, "https://github.com/<redacted>")
            raise subprocess.CalledProcessError(
                result.returncode, "git push", result.stdout, safe_stderr
            )
