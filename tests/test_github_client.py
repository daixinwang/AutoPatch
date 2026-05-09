"""
tests/test_github_client.py
----------------------------
Tests for github_client.parse_github_url and GitHubIssue.to_prompt_text.
No network access required.
"""

import pytest

from github_client import GitHubIssue, RepoInfo, parse_github_url


# ── parse_github_url ────────────────────────────────────────


class TestParseGithubUrl:
    def test_parse_shorthand(self):
        info = parse_github_url("owner/repo")
        assert info.owner == "owner"
        assert info.repo == "repo"
        assert info.clone_url == "https://github.com/owner/repo.git"
        assert info.ssh_url == "git@github.com:owner/repo.git"

    def test_parse_https_url(self):
        info = parse_github_url("https://github.com/owner/repo")
        assert info.owner == "owner"
        assert info.repo == "repo"

    def test_parse_https_with_git(self):
        info = parse_github_url("https://github.com/owner/repo.git")
        assert info.owner == "owner"
        assert info.repo == "repo"

    def test_parse_ssh_url(self):
        info = parse_github_url("git@github.com:owner/repo.git")
        assert info.owner == "owner"
        assert info.repo == "repo"

    def test_parse_invalid_url(self):
        with pytest.raises(ValueError):
            parse_github_url("https://gitlab.com/owner/repo")


# ── GitHubIssue.to_prompt_text ──────────────────────────────


class TestIssueToPromptText:
    def test_issue_to_prompt_text(self):
        issue = GitHubIssue(
            number=42,
            title="Fix the widget",
            body="The widget is broken when clicking save.",
            state="open",
            labels=["bug", "urgent"],
            comments=["I can reproduce this.", "Same here."],
            html_url="https://github.com/owner/repo/issues/42",
        )
        text = issue.to_prompt_text()

        assert "Issue #42" in text
        assert "Fix the widget" in text
        assert "The widget is broken when clicking save." in text
        assert "bug" in text
        assert "urgent" in text
        assert "I can reproduce this." in text
        assert "Same here." in text
        assert "open" in text


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
