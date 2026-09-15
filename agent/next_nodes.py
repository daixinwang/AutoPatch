"""Failure-aware node implementations, with injectable structured model calls."""

import json
import logging
import os
import subprocess
from pathlib import Path

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from agent.failure import LIMITS, deterministic_diagnosis, diagnosis, recovery_action
from agent.models import (
    ExecutionPlan,
    FailureDiagnosis,
    ProjectProfile,
    TestCommandResult,
    TestPlan,
    TestReport,
)
from core.execution import get_backend
from core.project_profile import profile_project
from core.test_pipeline import execute_plan
from tools.workspace import get_workspace


def structured_call(llm, schema, messages):
    """Validate native tool output, with at most two format-only regenerations."""
    output = llm.with_structured_output(schema)
    instruction = (
        f"Call the {schema.__name__} tool with valid JSON arguments matching its schema. "
        "Use JSON arrays and objects, never XML tags or attributes. Return a concise complete result."
    )
    for attempt in range(3):
        feedback = "" if attempt == 0 else "The previous response failed schema validation. Regenerate it. "
        # Do not replay malformed tool calls: they have no matching tool result.
        request = [*messages, HumanMessage(content=feedback + instruction)]
        try:
            return schema.model_validate(output.invoke(request))
        except (ValidationError, OutputParserException) as exc:
            logging.getLogger(__name__).warning(
                "%s structured response invalid (attempt %d/3)", schema.__name__, attempt + 1
            )
            if attempt == 2:
                raise ValueError(f"Invalid {schema.__name__} response after 3 attempts") from exc


def event(state, kind, **data):
    return {"trace_events": [*state.get("trace_events", []), {"type": kind, **data}]}


def context(state):
    try:
        files = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], cwd=get_workspace(), capture_output=True, text=True, timeout=5
        ).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        files = []
    keys = (
        "issue_task",
        "execution_plan",
        "test_report",
        "review_decision",
        "failure_diagnosis",
        "coder_retries",
        "replans",
        "test_replans",
        "environment_recoveries",
    )
    data = {key: state.get(key) for key in keys}
    data["changed_files"] = files
    data["recent_tool_errors"] = [
        str(m.content)[-1000:]
        for m in state.get("messages", [])[-10:]
        if getattr(m, "type", "") == "tool" and "error" in str(m.content).lower()
    ]
    return json.dumps(data, ensure_ascii=False)


def project_profile_node(state):
    profile = profile_project(Path(get_workspace()))
    return {
        "project_profile": profile.model_dump(),
        "repo_language": profile.primary_language,
        **event(state, "project_profiled", profile=profile.model_dump()),
    }


def plan_node(state, llm, call, replan=False):
    prompt = (
        "Revise the previous plan using failure evidence. Preserve valid assumptions, list rejected "
        "assumptions and new steps. Do not edit code."
        if replan
        else "Plan a minimal source-only repair for the issue. Never modify tests."
    )
    plan = call(llm, ExecutionPlan, [SystemMessage(content=prompt), HumanMessage(content=context(state))])
    result = {
        "execution_plan": plan.model_dump(),
        "plan": plan.model_dump_json(),
        "coder_steps": 0,
        "messages": [HumanMessage(content="Implement this validated plan:\n" + plan.model_dump_json())],
    }
    if replan:
        result.update(event(state, "replan_finished", plan=plan.model_dump()))
    return result


def test_plan_node(state, llm, call):
    profile = ProjectProfile.model_validate(state["project_profile"])
    try:
        plan = call(
            llm,
            TestPlan,
            [
                SystemMessage(
                    content=(
                        "Select test command IDs only from the supplied profile. No shell commands. "
                        "Choose full regression tests unless a targeted pytest path is known. "
                        "An empty targeted_paths list runs the full suite."
                    )
                ),
                HumanMessage(content=profile.model_dump_json() + "\n" + context(state)),
            ],
        )
    except (ValueError, TypeError):
        plan = TestPlan(
            commands=profile.default_test_commands, reason="Invalid structured selection; use detected suite"
        )
    return {"test_plan": plan.model_dump(), **event(state, "test_plan_created", plan=plan.model_dump())}


def test_execute_node(state):
    profile = ProjectProfile.model_validate(state["project_profile"])
    plan = TestPlan.model_validate(state["test_plan"])
    try:
        backend = get_backend()
        if state.get("execution_image"):
            from core.execution.docker import DockerSandboxBackend

            backend = DockerSandboxBackend(
                state["execution_image"], state.get("execution_python"), state.get("execution_workspace", "/workspace")
            )
        report = execute_plan(profile, plan, Path(get_workspace()), backend)
    except ValueError as exc:
        report = TestReport(
            project_type=profile.primary_language,
            all_required_passed=False,
            results=[TestCommandResult(command="selection", exit_code=None, status="error", stderr_summary=str(exc))]
            if profile.default_test_commands
            else [],
        )
    return {
        "test_report": report.model_dump(),
        "test_output": report.model_dump_json(),
        "review_decision": None,
        "terminal_status": "running",
        **event(state, "test_executed", report=report.model_dump()),
    }


def failure_classifier_node(state, llm, call):
    report = TestReport.model_validate(state["test_report"])
    failure = deterministic_diagnosis(report)
    if failure is None:
        try:
            failure = call(
                llm,
                FailureDiagnosis,
                [
                    SystemMessage(
                        content=(
                            "Diagnose the failure from evidence. Distinguish implementation errors from wrong plans, "
                            "test selection, dependencies, environment failures and insufficient context. "
                            "Do not infer infrastructure failure from an ordinary assertion failure."
                        )
                    ),
                    HumanMessage(content=context(state)),
                ],
            )
        except (ValueError, TypeError):
            failure = diagnosis("unrecoverable", ["Invalid structured failure diagnosis"])
    action = recovery_action(failure, state)
    result = {
        "failure_diagnosis": failure.model_dump(),
        "recovery_action": action,
        "coder_steps": 0,
        "review_result": "REJECT: " + "; ".join(failure.evidence),
        "messages": [HumanMessage(content="Failure diagnosis:\n" + failure.model_dump_json())],
        **event(state, "failure_classified", diagnosis=failure.model_dump(), action=action),
    }
    if action in LIMITS:
        counter = LIMITS[action][0]
        result[counter] = state.get(counter, 0) + 1
    else:
        result["terminal_status"] = (
            "infra_error" if failure.failure_type in ("environment_error", "dependency_error") else "failed"
        )
    return result


def environment_recovery_node(state):
    recovery_image = os.getenv("AUTOPATCH_RECOVERY_IMAGE", "")
    if recovery_image:
        return {
            "execution_image": recovery_image,
            "recovery_action": "rerun_tests",
            **event(state, "environment_recovery", status="prepared_image_selected"),
        }
    # No model-generated pip/npm installs. Operator supplies a prebuilt dependency image.
    # Stop explicitly when that image cannot satisfy imports; do not mutate host deps.
    return {
        "terminal_status": "infra_error",
        "recovery_action": "stop",
        "review_result": "REJECT: dependency recovery requires an operator-prepared sandbox image",
        **event(state, "environment_recovery", status="operator_required"),
    }
