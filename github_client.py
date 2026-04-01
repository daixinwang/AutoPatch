"""
github_client.py
----------------
GitHub API 封装层。

职责：
  1. 解析 GitHub Repo URL（支持 https 和 ssh 格式）
  2. 通过 GitHub REST API 拉取 Issue 详情（标题、正文、评论）
  3. 将目标仓库 clone 到本地临时目录，作为 Agent 的工作空间
  4. 所有网络操作均有超时和错误处理

依赖：
  - requests（HTTP 客户端）
  - gitpython（git clone 操作）
  - python-dotenv（读取 GITHUB_TOKEN）
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 常量 ──────────────────────────────────────
GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 30  # 秒


# ══════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════

@dataclass
class GitHubIssue:
    """GitHub Issue 的结构化表示。"""
    number: int
    title: str
    body: str
    state: str                        # "open" | "closed"
    labels: List[str] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    html_url: str = ""

    def to_prompt_text(self) -> str:
        """
        将 Issue 内容转换为适合作为 Agent 输入的结构化文本。

        Returns:
            格式化的 Issue 描述字符串
        """
        lines = [
            f"# Issue #{self.number}: {self.title}",
            f"URL: {self.html_url}",
            f"状态: {self.state}",
        ]
        if self.labels:
            lines.append(f"标签: {', '.join(self.labels)}")

        lines.append("\n## Issue 正文\n")
        lines.append(self.body or "（无正文）")

        if self.comments:
            lines.append(f"\n## 评论（共 {len(self.comments)} 条）\n")
            for i, comment in enumerate(self.comments, 1):
                # 每条评论截断到 500 字符，避免 prompt 过长
                preview = comment[:500] + "..." if len(comment) > 500 else comment
                lines.append(f"### 评论 {i}\n{preview}\n")

        return "\n".join(lines)


@dataclass
class RepoInfo:
    """解析后的仓库信息。"""
    owner: str
    repo: str
    clone_url: str
    ssh_url: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def api_base(self) -> str:
        return f"{GITHUB_API_BASE}/repos/{self.owner}/{self.repo}"


# ══════════════════════════════════════════════
# URL 解析
# ══════════════════════════════════════════════

def parse_github_url(url: str) -> RepoInfo:
    """
    解析 GitHub 仓库 URL，提取 owner 和 repo 名称。

    支持格式：
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
      - owner/repo（简写格式）

    Args:
        url: GitHub 仓库 URL 或 owner/repo 简写

    Returns:
        RepoInfo 数据对象

    Raises:
        ValueError: URL 格式无法识别时抛出
    """
    url = url.strip().rstrip("/")

    # 简写格式：owner/repo
    if re.match(r"^[\w.-]+/[\w.-]+$", url):
        owner, repo = url.split("/", 1)
        repo = repo.removesuffix(".git")
        return RepoInfo(
            owner=owner,
            repo=repo,
            clone_url=f"https://github.com/{owner}/{repo}.git",
            ssh_url=f"git@github.com:{owner}/{repo}.git",
        )

    # SSH 格式：git@github.com:owner/repo.git
    ssh_match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
    if ssh_match:
        owner, repo = ssh_match.group(1), ssh_match.group(2)
        return RepoInfo(
            owner=owner,
            repo=repo,
            clone_url=f"https://github.com/{owner}/{repo}.git",
            ssh_url=url if url.endswith(".git") else url + ".git",
        )

    # HTTPS 格式：https://github.com/owner/repo[.git]
    parsed = urlparse(url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError(f"不支持非 GitHub 的 URL: {url}")

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"无法从 URL 中解析出 owner/repo: {url}")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return RepoInfo(
        owner=owner,
        repo=repo,
        clone_url=f"https://github.com/{owner}/{repo}.git",
        ssh_url=f"git@github.com:{owner}/{repo}.git",
    )


# ══════════════════════════════════════════════
# GitHub API 客户端
# ══════════════════════════════════════════════

class GitHubClient:
    """
    GitHub REST API v3 客户端。

    自动从环境变量 GITHUB_TOKEN 读取 Personal Access Token。
    未设置 Token 时仍可使用，但会受到 60 req/h 的匿名限速。
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AutoPatch-Agent/1.0",
        })
        if self._token:
            self._session.headers["Authorization"] = f"Bearer {self._token}"
            print(f"  [GitHubClient] 已加载 GitHub Token（末4位: ...{self._token[-4:]}）")
        else:
            print("  [GitHubClient] ⚠️  未设置 GITHUB_TOKEN，使用匿名访问（限速 60 req/h）")

    def _get(self, url: str) -> Union[dict, list]:
        """
        发送 GET 请求并返回 JSON 结果。

        Args:
            url: 完整的 API URL

        Returns:
            解析后的 JSON 数据

        Raises:
            requests.HTTPError: API 返回错误状态码时抛出
        """
        resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def fetch_issue(self, repo_info: RepoInfo, issue_number: int) -> GitHubIssue:
        """
        拉取指定 Issue 的详细信息（标题、正文、标签）及其所有评论。

        Args:
            repo_info:     目标仓库信息
            issue_number:  Issue 编号

        Returns:
            GitHubIssue 结构化对象

        Raises:
            requests.HTTPError: Issue 不存在或无权访问时抛出
        """
        print(f"  [GitHubClient] 拉取 Issue #{issue_number} from {repo_info.full_name}...")

        # 拉取 Issue 基本信息
        issue_url = f"{repo_info.api_base}/issues/{issue_number}"
        data = self._get(issue_url)

        labels = [lbl["name"] for lbl in data.get("labels", [])]

        # 拉取评论
        comments: list[str] = []
        comments_url = data.get("comments_url", "")
        if comments_url and data.get("comments", 0) > 0:
            print(f"  [GitHubClient] 拉取 {data['comments']} 条评论...")
            comments_data = self._get(comments_url)
            if isinstance(comments_data, list):
                comments = [c.get("body", "") for c in comments_data if c.get("body")]

        issue = GitHubIssue(
            number=issue_number,
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            state=data.get("state", "unknown"),
            labels=labels,
            comments=comments,
            html_url=data.get("html_url", ""),
        )

        print(f"  [GitHubClient] ✅ Issue 拉取成功: [{issue.state}] {issue.title}")
        return issue

    def fetch_repo_metadata(self, repo_info: RepoInfo) -> dict:
        """
        拉取仓库基本元数据（语言、默认分支、描述等）。

        Args:
            repo_info: 目标仓库信息

        Returns:
            仓库元数据字典
        """
        print(f"  [GitHubClient] 拉取仓库元数据: {repo_info.full_name}...")
        data = self._get(repo_info.api_base)
        return {
            "default_branch": data.get("default_branch", "main"),
            "language":       data.get("language", "Unknown"),
            "description":    data.get("description", ""),
            "stars":          data.get("stargazers_count", 0),
            "private":        data.get("private", False),
        }


# ══════════════════════════════════════════════
# 仓库克隆管理
# ══════════════════════════════════════════════

class RepoWorkspace:
    """
    管理目标仓库的本地工作空间。

    使用 git clone 拉取仓库到临时目录，Agent 在此目录内操作文件。
    支持作为上下文管理器使用，退出时自动清理临时目录。

    用法：
        with RepoWorkspace(repo_info) as workspace:
            print(workspace.path)   # 本地仓库路径
    """

    def __init__(
        self,
        repo_info: RepoInfo,
        target_dir: Optional[str] = None,
        branch: Optional[str] = None,
        depth: int = 1,
    ) -> None:
        """
        Args:
            repo_info:  目标仓库信息
            target_dir: 指定 clone 到的目录（默认创建系统临时目录）
            branch:     clone 指定分支（默认仓库默认分支）
            depth:      clone 深度（默认 1 做浅克隆，节省时间和空间）
        """
        self.repo_info = repo_info
        self.branch = branch
        self.depth = depth
        self._owns_dir = target_dir is None  # 是否由本对象负责清理目录

        if target_dir:
            self.path = Path(target_dir)
            self.path.mkdir(parents=True, exist_ok=True)
        else:
            self.path = Path(tempfile.mkdtemp(prefix=f"autopatch_{repo_info.repo}_"))

        self._cloned = False

    def clone(self) -> Path:
        """
        执行 git clone 操作。

        Returns:
            克隆后的本地仓库路径

        Raises:
            RuntimeError: clone 失败时抛出，包含 git 错误输出
        """
        print(f"\n📥 [RepoWorkspace] 开始 clone: {self.repo_info.clone_url}")
        print(f"   目标目录: {self.path}")

        cmd = ["git", "clone", "--depth", str(self.depth)]
        if self.branch:
            cmd += ["--branch", self.branch]
        cmd += [self.repo_info.clone_url, str(self.path)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"git clone 失败 (exit {result.returncode}):\n{result.stderr}"
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"git clone 超时（超过 300 秒）: {self.repo_info.clone_url}")

        self._cloned = True
        print(f"✅ [RepoWorkspace] clone 完成 → {self.path}")
        return self.path

    def get_tracked_files(self) -> list[str]:
        """
        获取仓库中所有被 git 追踪的文件列表。

        Returns:
            相对路径列表
        """
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(self.path),
            capture_output=True,
            text=True,
        )
        return result.stdout.strip().splitlines() if result.returncode == 0 else []

    def cleanup(self) -> None:
        """删除临时工作目录（仅当由本对象创建时才删除）。"""
        if self._owns_dir and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
            print(f"🗑️  [RepoWorkspace] 已清理临时目录: {self.path}")

    def __enter__(self) -> "RepoWorkspace":
        self.clone()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
