"""
tests/test_api_models.py
------------------------
Unit tests for API request and response model boundaries.
"""

from api.models import ApplyRequest, PatchRequest, PreviewResponse, ResumeRequest


def test_patch_request_accepts_repo_and_issue_number():
    req = PatchRequest(repoUrl="owner/repo", issueNumber=42)

    assert req.repoUrl == "owner/repo"
    assert req.issueNumber == 42


def test_resume_request_exposes_task_id():
    req = ResumeRequest(taskId="task-123")

    assert req.taskId == "task-123"


def test_apply_request_includes_diff_content():
    req = ApplyRequest(repoUrl="owner/repo", issueNumber=7, diffContent="diff --git")

    assert req.repoUrl == "owner/repo"
    assert req.issueNumber == 7
    assert req.diffContent == "diff --git"


def test_preview_response_keeps_frontend_schema():
    resp = PreviewResponse(
        issueTitle="Bug",
        issueBody="Steps",
        issueState="open",
        issueLabels=["bug"],
        commentCount=2,
        issueUrl="https://github.com/owner/repo/issues/1",
        repoLanguage="Python",
        repoStars=10,
        repoPrivate=False,
        repoDescription="Demo",
        defaultBranch="main",
    )

    assert resp.model_dump() == {
        "issueTitle": "Bug",
        "issueBody": "Steps",
        "issueState": "open",
        "issueLabels": ["bug"],
        "commentCount": 2,
        "issueUrl": "https://github.com/owner/repo/issues/1",
        "repoLanguage": "Python",
        "repoStars": 10,
        "repoPrivate": False,
        "repoDescription": "Demo",
        "defaultBranch": "main",
    }
