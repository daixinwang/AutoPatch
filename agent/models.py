"""Validated workflow contracts; store JSON dictionaries in checkpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


FailureType = Literal[
    "implementation_error",
    "wrong_plan",
    "test_selection_error",
    "dependency_error",
    "environment_error",
    "insufficient_context",
    "unrecoverable",
]
Action = Literal["retry_coder", "replan", "rerun_tests", "recover_environment", "stop"]


class PlanStep(Contract):
    id: str
    objective: str
    suspected_files: list[str] = Field(default_factory=list)
    validation_hint: str | None = None


class ExecutionPlan(Contract):
    summary: str
    steps: list[PlanStep] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    rejected_assumptions: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "medium"


class ProjectProfile(Contract):
    primary_language: str
    manifests: list[str] = Field(default_factory=list)
    test_frameworks: list[str] = Field(default_factory=list)
    default_test_commands: list[str] = Field(default_factory=list)
    src_layout: bool = False


class TestPlan(Contract):
    commands: list[str] = Field(max_length=8)
    reason: str
    targeted_paths: list[str] = Field(default_factory=list, max_length=20)


class TestCommandResult(Contract):
    command: str
    exit_code: int | None
    status: Literal["passed", "failed", "timeout", "unavailable", "error"]
    stdout_summary: str = ""
    stderr_summary: str = ""


class TestReport(Contract):
    project_type: str
    results: list[TestCommandResult]
    all_required_passed: bool

    @model_validator(mode="after")
    def consistent_success(self):
        passed = bool(self.results) and all(r.status == "passed" and r.exit_code == 0 for r in self.results)
        if self.all_required_passed != passed:
            raise ValueError("Success requires nonempty, successful command results")
        return self


class ReviewDecision(Contract):
    verdict: Literal["pass", "reject"]
    reasons: list[str]
    suspected_failure_type: FailureType | None = None


class FailureDiagnosis(Contract):
    failure_type: FailureType
    evidence: list[str]
    recommended_action: Action
    confidence: float = Field(ge=0, le=1)


def verified(state: dict) -> bool:
    """Fail closed for legacy, malformed, or incomplete records."""
    try:
        return (
            TestReport.model_validate(state.get("test_report")).all_required_passed
            and ReviewDecision.model_validate(state.get("review_decision")).verdict == "pass"
            and state.get("terminal_status") == "resolved"
        )
    except (ValueError, TypeError):
        return False
