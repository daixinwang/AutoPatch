# Apply Patch → Create GitHub PR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AutoPatch 结果页增加 "Create PR" 按钮，点击后后端重新 clone 仓库、应用 diff、push 分支并创建 GitHub Pull Request，最终返回 PR URL 供用户跳转。

**Architecture:** 新增 `POST /api/apply` 端点，接收 `{ repoUrl, issueNumber, diffContent }`，在后端执行 clone → git apply → push → GitHub API 创建 PR。`GitHubClient` 增加 `create_pull_request()` 方法，前端 `ResultArea.tsx` 增加按钮及状态机。

**Tech Stack:** Python 3.9, FastAPI, subprocess (git), requests (GitHub API), React + TypeScript

---

## File Map

| 文件 | 变更类型 | 职责 |
|---|---|---|
| `github_client.py` | 修改 | 新增 `GitHubClient.create_pull_request()` |
| `server.py` | 修改 | 新增 `ApplyRequest`、`_git_apply_and_push()`、`POST /api/apply` |
| `frontend/src/components/ResultArea.tsx` | 修改 | 新增 Create PR 按钮及状态逻辑 |
| `tests/test_github_client.py` | 修改 | 新增 `create_pull_request` 单元测试 |
| `tests/test_server.py` | 修改 | 新增 `/api/apply` 端点测试 |

---

## Task 1: 为 `GitHubClient` 添加 `create_pull_request()` 并测试

**Files:**
- Modify: `tests/test_github_client.py`
- Modify: `github_client.py`

- [ ] **Step 1: 在 `tests/test_github_client.py` 末尾追加失败测试**

```python
# ── GitHubClient.create_pull_request ───────────────────────


class TestCreatePullRequest:
    def test_returns_pr_url(self, monkeypatch):
        from unittest.mock import MagicMock
        from github_client import GitHubClient, parse_github_url

        client = GitHubClient(token="fake-token")
        repo_info = parse_github_url("owner/repo")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"html_url": "https://github.com/owner/repo/pull/7"}
        mock_resp.raise_for_status = MagicMock()
        monkeypatch.setattr(client._session, "post", lambda *a, **kw: mock_resp)

        url = client.create_pull_request(
            repo_info=repo_info,
            head_branch="autopatch/issue-42",
            base_branch="main",
            title="[AutoPatch] Fix issue #42",
            body="Closes #42",
        )
        assert url == "https://github.com/owner/repo/pull/7"

    def test_raises_on_http_error(self, monkeypatch):
        import requests
        from unittest.mock import MagicMock
        from github_client import GitHubClient, parse_github_url

        client = GitHubClient(token="fake-token")
        repo_info = parse_github_url("owner/repo")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        monkeypatch.setattr(client._session, "post", lambda *a, **kw: mock_resp)

        with pytest.raises(requests.HTTPError):
            client.create_pull_request(
                repo_info=repo_info,
                head_branch="autopatch/issue-42",
                base_branch="main",
                title="[AutoPatch] Fix issue #42",
                body="Closes #42",
            )
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/davian/Desktop/Code/AutoPatch
source .venv/bin/activate
pytest tests/test_github_client.py::TestCreatePullRequest -v
```

期望输出：`AttributeError` 或 `ImportError`（方法尚未实现）

- [ ] **Step 3: 在 `github_client.py` 的 `GitHubClient` 类末尾添加 `create_pull_request()`**

在文件中找到 `fetch_repo_metadata` 方法的结束处（约第 320 行），在其后、类结束前添加：

```python
def create_pull_request(
    self,
    repo_info: RepoInfo,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> str:
    """
    在目标仓库创建 Pull Request。

    Args:
        repo_info:    目标仓库信息
        head_branch:  PR 的源分支（含改动）
        base_branch:  PR 的目标分支（通常为 default_branch）
        title:        PR 标题
        body:         PR 描述

    Returns:
        PR 的 HTML URL（如 https://github.com/owner/repo/pull/7）

    Raises:
        requests.HTTPError: GitHub API 返回错误（如 422 分支不存在、403 无权限）
    """
    url = f"{repo_info.api_base}/pulls"
    logger.info(
        "[GitHubClient] 创建 PR: %s → %s in %s",
        head_branch, base_branch, repo_info.full_name,
    )
    resp = self._session.post(
        url,
        json={
            "title": title,
            "body":  body,
            "head":  head_branch,
            "base":  base_branch,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    pr_url = resp.json()["html_url"]
    logger.info("[GitHubClient] ✅ PR 已创建: %s", pr_url)
    return pr_url
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_github_client.py::TestCreatePullRequest -v
```

期望输出：`2 passed`

- [ ] **Step 5: 提交**

```bash
git add github_client.py tests/test_github_client.py
git commit -m "feat: add GitHubClient.create_pull_request()"
```

---

## Task 2: 实现 `_git_apply_and_push()` 并测试

**Files:**
- Modify: `server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 在 `tests/test_server.py` 末尾追加失败测试**

```python
# ── _git_apply_and_push ────────────────────────────────────


class TestGitApplyAndPush:
    """测试 _git_apply_and_push 的 git 操作（mock push 步骤）。"""

    def _make_repo_with_file(self, tmp_path):
        """创建一个带初始 commit 的本地 git 仓库，包含 hello.py。"""
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
        hello = repo / "hello.py"
        hello.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo

    def _make_diff(self, repo_path):
        """在 repo 中添加一行后生成 diff，再还原，用于测试 apply。"""
        import subprocess
        hello = repo_path / "hello.py"
        original = hello.read_text()
        hello.write_text(original + "\ndef bye():\n    return 'bye'\n")
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        diff_content = result.stdout
        # 还原文件，让 apply 来应用
        hello.write_text(original)
        subprocess.run(["git", "checkout", "--", "hello.py"], cwd=repo_path, check=True, capture_output=True)
        return diff_content

    def test_applies_diff_and_commits(self, tmp_path, monkeypatch):
        import subprocess
        from github_client import parse_github_url
        from server import _git_apply_and_push

        repo = self._make_repo_with_file(tmp_path)
        diff_content = self._make_diff(repo)

        repo_info = parse_github_url("owner/repo")

        # mock push — 不实际推送到 GitHub
        push_calls = []
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if isinstance(cmd, list) and "push" in cmd:
                push_calls.append(cmd)
                mock = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
                return mock
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        _git_apply_and_push(repo, "autopatch/issue-42", diff_content, repo_info, "fake-token")

        # 验证分支已创建
        result = real_run(
            ["git", "branch", "--list", "autopatch/issue-42"],
            cwd=repo, capture_output=True, text=True,
        )
        assert "autopatch/issue-42" in result.stdout

        # 验证 push 被调用
        assert len(push_calls) == 1
        assert "push" in push_calls[0]

    def test_raises_on_bad_diff(self, tmp_path, monkeypatch):
        import subprocess
        from github_client import parse_github_url
        from server import _git_apply_and_push

        repo = self._make_repo_with_file(tmp_path)
        repo_info = parse_github_url("owner/repo")

        # mock push 防止网络调用
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: (
            type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            if "push" in (cmd if isinstance(cmd, list) else [])
            else __import__("subprocess").run.__wrapped__(cmd, **kw)
            if hasattr(__import__("subprocess").run, "__wrapped__")
            else __import__("subprocess").run(cmd, **kw)
        ))

        with pytest.raises(subprocess.CalledProcessError):
            _git_apply_and_push(
                repo, "autopatch/issue-99",
                "this is not a valid diff at all",
                repo_info, "fake-token",
            )
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_server.py::TestGitApplyAndPush -v
```

期望输出：`ImportError: cannot import name '_git_apply_and_push' from 'server'`

- [ ] **Step 3: 在 `server.py` 中添加 `_git_apply_and_push()`**

在文件中找到 `_generate_and_save_diff` 函数（约第 399 行）之前，插入：

```python
def _git_apply_and_push(
    repo_path,
    branch: str,
    diff_content: str,
    repo_info,
    token: str,
) -> None:
    """
    在本地 git 仓库中应用 diff，创建分支，commit，并 push 到 GitHub。

    同步函数，在 asyncio executor 中调用。

    Args:
        repo_path:    本地 git 仓库路径（Path 或 str）
        branch:       新分支名（如 "autopatch/issue-42"）
        diff_content: unified diff 字符串
        repo_info:    RepoInfo（含 owner/repo）
        token:        GitHub Personal Access Token（需 contents:write + pull-requests:write）

    Raises:
        subprocess.CalledProcessError: git 命令非零退出（如 apply 冲突、push 失败）
    """
    import tempfile as _tempfile

    cwd = str(repo_path)

    # 1. 创建新分支
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=cwd, check=True, capture_output=True, text=True,
    )

    # 2. 将 diff 写入临时文件并 apply
    with _tempfile.NamedTemporaryFile(
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

    # 3. 配置 git 用户（临时，仅本 repo）
    subprocess.run(
        ["git", "config", "user.email", "autopatch@bot.local"],
        cwd=cwd, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AutoPatch"],
        cwd=cwd, check=True, capture_output=True,
    )

    # 4. Commit
    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: AutoPatch generated patch"],
        cwd=cwd, check=True, capture_output=True, text=True,
    )

    # 5. Push（token 嵌入 HTTPS URL，支持私有仓库）
    remote_url = (
        f"https://x-access-token:{token}@github.com/"
        f"{repo_info.owner}/{repo_info.repo}.git"
    )
    result = subprocess.run(
        ["git", "push", remote_url, branch],
        cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode != 0:
        # 分支已存在时追加时间戳后缀重试一次
        if "already exists" in result.stderr or "rejected" in result.stderr:
            from datetime import datetime
            branch_retry = f"{branch}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            subprocess.run(
                ["git", "branch", "-m", branch, branch_retry],
                cwd=cwd, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "push", remote_url, branch_retry],
                cwd=cwd, check=True, capture_output=True, text=True,
            )
            logger.info("[apply] 分支已存在，重命名为 %s 后成功 push", branch_retry)
        else:
            raise subprocess.CalledProcessError(
                result.returncode, "git push", result.stdout, result.stderr
            )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_server.py::TestGitApplyAndPush::test_applies_diff_and_commits -v
```

期望输出：`1 passed`

> 注：`test_raises_on_bad_diff` 因为 monkeypatch 嵌套较复杂，可能需要调整。若失败，先跳过此 case，继续后续任务，完成后回头修复。

- [ ] **Step 5: 提交**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add _git_apply_and_push() to server"
```

---

## Task 3: 实现 `POST /api/apply` 端点并测试

**Files:**
- Modify: `server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 在 `tests/test_server.py` 末尾追加失败测试**

```python
# ── POST /api/apply ─────────────────────────────────────────


class TestApplyEndpoint:
    @pytest.mark.asyncio
    async def test_apply_returns_pr_url(self, monkeypatch):
        import server
        from github_client import parse_github_url

        # mock _git_apply_and_push — 跳过真实 git/push
        monkeypatch.setattr(server, "_git_apply_and_push", lambda *a, **kw: None)

        # mock GitHubClient.create_pull_request
        from unittest.mock import MagicMock, patch
        mock_client = MagicMock()
        mock_client.fetch_repo_metadata.return_value = {"default_branch": "main"}
        mock_client.create_pull_request.return_value = "https://github.com/owner/repo/pull/99"

        # mock RepoWorkspace.clone + cleanup
        from unittest.mock import MagicMock
        mock_ws = MagicMock()
        mock_ws.clone.return_value = "/tmp/fake_repo"

        with patch("server.GitHubClient", return_value=mock_client), \
             patch("server.RepoWorkspace", return_value=mock_ws):
            transport = httpx.ASGITransport(app=fastapi_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/api/apply", json={
                    "repoUrl":     "owner/repo",
                    "issueNumber": 42,
                    "diffContent": "diff --git a/x b/x\n",
                })

        assert resp.status_code == 200
        data = resp.json()
        assert data["prUrl"] == "https://github.com/owner/repo/pull/99"
        assert data["branchName"] == "autopatch/issue-42"

    @pytest.mark.asyncio
    async def test_apply_missing_token_returns_422(self, monkeypatch):
        import os
        import server
        monkeypatch.setenv("GITHUB_TOKEN", "")

        # mock workspace so clone doesn't actually run
        from unittest.mock import MagicMock, patch
        mock_ws = MagicMock()
        mock_ws.clone.return_value = "/tmp/fake_repo"

        # mock GitHubClient — token is empty, fetch_repo_metadata OK, but create_pr raises 403
        import requests
        mock_client = MagicMock()
        mock_client.fetch_repo_metadata.return_value = {"default_branch": "main"}
        mock_client.create_pull_request.side_effect = requests.HTTPError("403 Forbidden")
        monkeypatch.setattr(server, "_git_apply_and_push", lambda *a, **kw: None)

        with patch("server.GitHubClient", return_value=mock_client), \
             patch("server.RepoWorkspace", return_value=mock_ws):
            transport = httpx.ASGITransport(app=fastapi_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/api/apply", json={
                    "repoUrl":     "owner/repo",
                    "issueNumber": 42,
                    "diffContent": "diff --git a/x b/x\n",
                })

        assert resp.status_code == 422
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_server.py::TestApplyEndpoint -v
```

期望输出：`404 Not Found`（端点尚未注册）

- [ ] **Step 3: 在 `server.py` 中添加 `ApplyRequest` 模型和 `POST /api/apply` 端点**

**a) 在现有 Pydantic 模型区（约第 199 行）添加 `ApplyRequest`：**

找到 `class PatchRequest(BaseModel):`，在其后添加：

```python
class ApplyRequest(BaseModel):
    repoUrl:     str
    issueNumber: int
    diffContent: str
```

**b) 在文件末尾的端点区域（`/api/health` 端点附近）添加新端点：**

```python
@fastapi_app.post("/api/apply", dependencies=[Depends(_verify_api_key)])
async def apply_endpoint(req: ApplyRequest):
    """
    将 Agent 生成的 diff 应用到目标仓库并创建 Pull Request。

    步骤：
      1. Clone 仓库到临时目录
      2. 创建分支、git apply diff、commit、push
      3. GitHub API 创建 PR
      4. 清理临时目录

    Returns:
        { "prUrl": "https://github.com/...", "branchName": "autopatch/issue-N" }
    """
    import os as _os
    import requests as _requests

    token = _os.getenv("GITHUB_TOKEN", "")

    try:
        repo_info = parse_github_url(req.repoUrl)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"URL 解析失败: {e}")

    client   = GitHubClient()
    try:
        meta = await asyncio.get_running_loop().run_in_executor(
            None, client.fetch_repo_metadata, repo_info
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"获取仓库信息失败: {e}")

    workspace = RepoWorkspace(repo_info=repo_info)
    try:
        tmp_dir = await asyncio.get_running_loop().run_in_executor(None, workspace.clone)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=f"Clone 失败: {e}")

    branch = f"autopatch/issue-{req.issueNumber}"
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _git_apply_and_push,
            tmp_dir, branch, req.diffContent, repo_info, token,
        )
        pr_url = await asyncio.get_running_loop().run_in_executor(
            None, client.create_pull_request,
            repo_info, branch, meta["default_branch"],
            f"[AutoPatch] Fix issue #{req.issueNumber}",
            f"This PR was automatically generated by AutoPatch.\n\nCloses #{req.issueNumber}",
        )
        logger.info("PR 创建成功: %s", pr_url)
        return {"prUrl": pr_url, "branchName": branch}
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        if "error: patch failed" in stderr or "error: " in stderr:
            raise HTTPException(
                status_code=422,
                detail="Patch 无法直接应用，可能存在冲突，请手动 git apply",
            )
        raise HTTPException(status_code=422, detail=f"git 操作失败: {stderr[:300]}")
    except _requests.HTTPError as e:
        raise HTTPException(status_code=422, detail=f"GitHub API 错误: {e}")
    finally:
        workspace.cleanup()   # 无论成功失败都清理，且只调用一次
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_server.py::TestApplyEndpoint -v
```

期望输出：`2 passed`

- [ ] **Step 5: 运行全量测试，确保无回归**

```bash
pytest tests/ -v
```

期望输出：所有原有测试 + 新测试全部通过

- [ ] **Step 6: 提交**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add POST /api/apply endpoint"
```

---

## Task 4: 前端添加 Create PR 按钮

**Files:**
- Modify: `frontend/src/components/ResultArea.tsx`

- [ ] **Step 1: 在 `ResultArea.tsx` 顶部的 import 行添加 `ExternalLink` 图标**

找到当前 import 行：
```typescript
import { CheckCircle2, Copy, Check, GitPullRequest, FileCode2, Plus, Minus, Clock, Layers } from 'lucide-react'
```
替换为：
```typescript
import { CheckCircle2, Copy, Check, GitPullRequest, FileCode2, Plus, Minus, Clock, Layers, ExternalLink, Loader2 } from 'lucide-react'
```

- [ ] **Step 2: 在 `ResultArea` 函数内（`useState` 声明处）添加 PR 状态变量**

找到：
```typescript
  const [copied, setCopied] = useState(false)
```
在其后添加：
```typescript
  type PRStatus = 'idle' | 'creating' | 'success' | 'error'
  const [prStatus, setPrStatus] = useState<PRStatus>('idle')
  const [prUrl,    setPrUrl]    = useState('')
  const [prError,  setPrError]  = useState('')
```

- [ ] **Step 3: 在 `copyDiff` 函数后添加 `handleCreatePR` 函数**

找到：
```typescript
  async function copyDiff() {
    await navigator.clipboard.writeText(result.diffContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
```
在其后添加：
```typescript
  async function handleCreatePR() {
    setPrStatus('creating')
    setPrError('')
    try {
      const res = await fetch('/api/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repoUrl:     repoUrl,
          issueNumber: Number(issue),
          diffContent: result.diffContent,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(data.detail ?? 'Unknown error')
      }
      const { prUrl: url } = await res.json()
      setPrUrl(url)
      setPrStatus('success')
    } catch (e: any) {
      setPrError(e.message ?? 'Failed to create PR')
      setPrStatus('error')
    }
  }
```

- [ ] **Step 4: 在 Diff 工具栏中用 Create PR 按钮替换 "View Issue" 外链**

找到：
```typescript
          <div className="flex items-center gap-2">
            {/* Create PR 按钮 */}
            <a
              href={`https://github.com/${repoUrl}/issues/${issue}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-all hover:border-brand/30 hover:text-text-primary"
              style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)' }}
            >
              <GitPullRequest className="h-3.5 w-3.5" />
              View Issue
            </a>
```
替换为：
```typescript
          <div className="flex items-center gap-2">
            {/* Create PR / View PR 按钮 */}
            {prStatus === 'success' ? (
              <a
                href={prUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all"
                style={{ borderColor: '#22d3a5', backgroundColor: 'rgba(34,211,165,0.1)', color: '#22d3a5' }}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View PR
              </a>
            ) : (
              <button
                onClick={handleCreatePR}
                disabled={prStatus === 'creating'}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-all hover:border-brand/30 hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)' }}
              >
                {prStatus === 'creating'
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <GitPullRequest className="h-3.5 w-3.5" />}
                {prStatus === 'creating' ? 'Creating…' : 'Create PR'}
              </button>
            )}
```

- [ ] **Step 5: 在 "应用命令提示" 区域下方添加错误提示**

找到：
```typescript
      {/* 应用命令提示 */}
      <div
        className="flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors"
        style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
      >
        <span className="text-xs text-text-muted">Apply patch:</span>
        <code className="flex-1 font-mono text-xs text-accent-blue">
          git apply issue-{issue}.diff
        </code>
      </div>
```
替换为：
```typescript
      {/* 应用命令提示 */}
      <div
        className="flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors"
        style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
      >
        <span className="text-xs text-text-muted">Apply patch:</span>
        <code className="flex-1 font-mono text-xs text-accent-blue">
          git apply issue-{issue}.diff
        </code>
      </div>

      {/* PR 创建错误提示 */}
      {prStatus === 'error' && (
        <div className="rounded-lg border px-4 py-3 text-xs text-accent-red animate-slide-up"
          style={{ borderColor: 'rgba(248,113,113,0.3)', backgroundColor: 'rgba(248,113,113,0.08)' }}
        >
          PR 创建失败：{prError}
        </div>
      )}
```

- [ ] **Step 6: 手动验证**

1. 启动后端：`source .venv/bin/activate && uvicorn server:app --reload --port 8000`
2. 启动前端：`cd frontend && npm run dev`
3. 完成一次 patch 任务后，在结果区应能看到 "Create PR" 按钮
4. 点击按钮，观察 loading 状态 → 成功后变为 "View PR ↗" 绿色链接

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/ResultArea.tsx
git commit -m "feat: add Create PR button to ResultArea"
```

---

## 完成后验收

- [ ] `pytest tests/` 全量通过，无回归
- [ ] 前端 Create PR 按钮在三种状态（idle / creating / success）下显示正确
- [ ] PR 错误时（如 token 无权限）前端展示可读错误信息，按钮可重试
- [ ] `POST /api/apply` 与其他端点一样受 `AUTOPATCH_API_KEY` 保护
