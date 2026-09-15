import os
import uuid

os.environ.setdefault("OPENAI_API_KEY", "offline-test-placeholder")

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from agent import graph


def test_graph_has_recovery_nodes():
    nodes = graph.build_graph().get_graph().nodes
    assert {
        "project_profile_node",
        "test_plan_node",
        "test_execute_node",
        "failure_classifier_node",
        "replanner_node",
        "environment_recovery_node",
    } <= nodes.keys()


@pytest.fixture(params=["memory", "postgres"])
def checkpoint(request):
    if request.param == "memory":
        yield MemorySaver()
    else:
        dsn = os.getenv("AUTOPATCH_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("PostgreSQL integration is opt-in")
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(dsn) as saver:
            saver.setup()
            yield saver


def test_wrong_plan_checkpoint_resume(tmp_workspace, monkeypatch, checkpoint):
    assert hasattr(graph, "replanner_node"), "Missing replanner"
    from agent.models import ExecutionPlan, PlanStep, TestCommandResult, TestReport

    (tmp_workspace / "pyproject.toml").touch()
    monkeypatch.setattr(graph, "index_builder_node", lambda s: {})
    monkeypatch.setattr(
        graph,
        "planner_node",
        lambda s: {
            "plan": "wrong",
            "execution_plan": ExecutionPlan(
                summary="wrong", steps=[PlanStep(id="1", objective="fix API")]
            ).model_dump(),
        },
    )
    monkeypatch.setattr(graph, "coder_node", lambda s: {"messages": [AIMessage(content="done")]})
    monkeypatch.setattr(graph, "test_plan_node", lambda s: {})

    def execute(s):
        passed = s.get("replans", 0) > 0
        result = TestCommandResult(
            command="python_pytest", exit_code=0 if passed else 1, status="passed" if passed else "failed"
        )
        return {
            "test_report": TestReport(project_type="Python", results=[result], all_required_passed=passed).model_dump()
        }

    monkeypatch.setattr(graph, "test_execute_node", execute)
    monkeypatch.setattr(
        graph,
        "structured_call",
        lambda llm, schema, messages: schema.model_validate(
            {"failure_type": "wrong_plan", "evidence": ["wrong layer"], "recommended_action": "replan", "confidence": 1}
            if schema.__name__ == "FailureDiagnosis"
            else {"summary": "fix service", "steps": [{"id": "2", "objective": "service"}]}
        ),
    )
    monkeypatch.setattr(
        graph,
        "reviewer_node",
        lambda s: {
            "review_decision": {"verdict": "pass", "reasons": []},
            "terminal_status": "resolved",
            "review_result": "PASS",
        },
    )
    app = graph.build_graph(checkpointer=checkpoint, interrupt_after=["replanner_node"])
    config = {"configurable": {"thread_id": "recovery-" + uuid.uuid4().hex}}
    initial = {"messages": [], "issue_task": "fix", "ablation": "full"}
    app.invoke(initial, config)
    assert app.get_state(config).values["replans"] == 1
    result = app.invoke(None, config)
    assert result["terminal_status"] == "resolved"
    assert result["execution_plan"]["summary"] == "fix service"


def test_no_tools_execute_when_sandboxed(monkeypatch):
    from tools.execute_tools import verify_importable

    monkeypatch.setenv("AUTOPATCH_EXECUTION_BACKEND", "docker")
    assert "SKIPPED" in verify_importable.invoke({"file_path": "foo.py"})


def test_retry_removes_unanswered_tool_calls(monkeypatch):
    observed = []

    class Coder:
        def invoke(self, messages):
            observed.extend(messages)
            return AIMessage(content="done")

    monkeypatch.setattr(graph, "_llm_with_tools", Coder())
    from langchain_core.messages import HumanMessage

    graph.coder_node(
        {
            "messages": [
                AIMessage(content="", tool_calls=[{"id": "abandoned", "name": "read_file", "args": {}}]),
                HumanMessage(content="failure"),
            ],
            "coder_retries": 1,
            "recovery_action": "retry_coder",
            "review_result": "REJECT: failed",
        }
    )
    assert not any(getattr(msg, "tool_calls", []) for msg in observed)


def test_controlled_recovery_uses_only_operator_image(monkeypatch):
    from agent.next_nodes import environment_recovery_node

    monkeypatch.setenv("AUTOPATCH_RECOVERY_IMAGE", "prepared-dependencies:v1")
    state = environment_recovery_node({"environment_recoveries": 1})
    assert state["execution_image"] == "prepared-dependencies:v1"
    assert state["recovery_action"] == "rerun_tests"
