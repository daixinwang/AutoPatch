"""
api/models.py
-------------
Pydantic request and response models for AutoPatch API endpoints.
"""

from pydantic import BaseModel


class PatchRequest(BaseModel):
    repoUrl: str
    issueNumber: int


class ResumeRequest(BaseModel):
    taskId: str


class ApplyRequest(BaseModel):
    repoUrl: str
    issueNumber: int
    diffContent: str


class PreviewResponse(BaseModel):
    issueTitle: str
    issueBody: str
    issueState: str
    issueLabels: list[str]
    commentCount: int
    issueUrl: str
    repoLanguage: str
    repoStars: int
    repoPrivate: bool
    repoDescription: str
    defaultBranch: str
