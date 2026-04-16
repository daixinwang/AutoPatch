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
