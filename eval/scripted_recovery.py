"""Offline fault injection. Real graph, subprocess tests, and patch validation.

Scripted decisions are NOT model-quality measurements. Never label these as
LLM results. Kept outside production graph and only selected by --mode scripted.
"""

import time
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent.failure import diagnosis
from agent.models import ExecutionPlan, PlanStep, TestPlan, TestReport
from core.execution.local import LocalTrustedBackend
from tools.workspace import reset_workspace, set_workspace


def run_scripted(case, workspace, ablation):
    from agent import graph, next_nodes

    scenario = case.raw.get("recovery_scenario")
    if scenario is None:
        raise ValueError("Scripted recovery requires a sanity-v3 scenario")
    started = time.monotonic()

    def structured(llm, schema, messages):
        if schema.__name__ == "FailureDiagnosis":
            return diagnosis(
                scenario if scenario in ("wrong_plan", "unrecoverable") else "implementation_error",
                ["scripted fault injection"],
            )
        return ExecutionPlan(summary="repair service", steps=[PlanStep(id="2", objective="repair service")])

    def planner(state):
        plan = ExecutionPlan(
            summary="repair API" if scenario == "wrong_plan" else "repair service",
            steps=[PlanStep(id="1", objective="initial plan")],
        )
        return {"execution_plan": plan.model_dump(), "plan": plan.model_dump_json()}

    attempts = 0

    def coder(state):
        nonlocal attempts
        attempts += 1
        fixed = scenario not in ("unrecoverable", "environment_error")
        if scenario == "wrong_plan":
            fixed = state["execution_plan"]["summary"] == "repair service"
        if scenario == "implementation_error" and attempts == 1:
            (workspace / "service.py").write_text("def add(a, b):\n    return a + abs(b)\n")
        elif fixed:
            (workspace / "service.py").write_text("def add(a, b):\n    return a + b\n")
        return {"messages": [AIMessage(content="scripted coder attempt")]}

    def test_planner(state):
        wrong = scenario == "test_selection_error" and not state.get("test_replans")
        return {
            "test_plan": TestPlan(
                commands=["go_test_all" if wrong else "python_pytest"], reason="scripted scope"
            ).model_dump()
        }

    def executor(state):
        if scenario == "environment_error":
            result = LocalTrustedBackend().run(["autopatch-nonexistent-toolchain"], workspace)
            report = TestReport(project_type="Python", results=[result], all_required_passed=False)
            return {"test_report": report.model_dump(), "test_output": report.model_dump_json()}
        return next_nodes.test_execute_node(state)

    token = set_workspace(str(workspace))
    try:
        with (
            patch.multiple(
                graph,
                index_builder_node=lambda s: {},
                planner_node=planner,
                coder_node=coder,
                test_plan_node=test_planner,
                test_execute_node=executor,
                structured_call=structured,
                reviewer_node=lambda s: {
                    "review_decision": {"verdict": "pass", "reasons": ["scripted review"]},
                    "review_result": "PASS",
                    "terminal_status": "resolved",
                },
            ),
            patch.object(next_nodes, "get_backend", return_value=LocalTrustedBackend()),
        ):
            app = graph.build_graph()
            state = {"messages": [], "issue_task": case.issue_markdown(), "ablation": ablation}
            steps = 0
            for update in app.stream(state, {"recursion_limit": 100}, stream_mode="updates"):
                steps += 1
                for value in update.values():
                    if value:
                        state.update({k: v for k, v in value.items() if k != "messages"})
            return {k: v for k, v in state.items() if k != "messages"} | {
                "step_count": steps,
                "elapsed_seconds": time.monotonic() - started,
                "decision_source": "scripted",
            }
    finally:
        reset_workspace(token)
