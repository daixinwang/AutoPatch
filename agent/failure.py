"""Deterministic evidence overrides and bounded recovery policy."""

import os

from agent.models import FailureDiagnosis, TestReport

ACTIONS = {
    "implementation_error": "retry_coder",
    "wrong_plan": "replan",
    "test_selection_error": "rerun_tests",
    "dependency_error": "recover_environment",
    "environment_error": "stop",
    "insufficient_context": "replan",
    "unrecoverable": "stop",
}
LIMITS = {
    "retry_coder": ("coder_retries", "MAX_REVIEW_RETRIES", 3),
    "replan": ("replans", "MAX_REPLANS", 2),
    "rerun_tests": ("test_replans", "MAX_TEST_REPLANS", 2),
    "recover_environment": ("environment_recoveries", "MAX_ENVIRONMENT_RECOVERIES", 1),
}


def diagnosis(kind, evidence):
    return FailureDiagnosis(failure_type=kind, evidence=evidence, recommended_action=ACTIONS[kind], confidence=1)


def deterministic_diagnosis(report: TestReport):
    if not report.results:
        return diagnosis("unrecoverable", ["No supported test command"])
    for result in report.results:
        text = result.stdout_summary + "\n" + result.stderr_summary
        if result.status == "unavailable":
            return diagnosis("environment_error", [text])
        if result.status == "error" or result.command == "python_pytest" and result.exit_code in (4, 5):
            return diagnosis("test_selection_error", [text])
        if "No module named pytest" in text:
            return diagnosis("dependency_error", [text])
        if result.status == "timeout":
            return diagnosis("unrecoverable", ["Test timeout", text])
    return None


def recovery_action(failure: FailureDiagnosis, state: dict):
    action = ACTIONS[failure.failure_type]  # Ignore a contradictory LLM action.
    if action == "replan" and state.get("ablation") == "no_replanner":
        action = "retry_coder"
    if action in LIMITS:
        counter, variable, default = LIMITS[action]
        if state.get(counter, 0) >= max(0, int(os.getenv(variable, str(default)))):
            return "stop"
    return action
