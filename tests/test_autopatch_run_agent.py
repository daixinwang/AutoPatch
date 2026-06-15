from autopatch import run_agent_on_issue


class _FakeAppWithNoneNode:
    def stream(self, initial_state, config, stream_mode):
        yield {"index_builder_node": None}
        yield {"planner_node": {"plan": "Inspect calculator.py"}}
        yield {"reviewer_node": {"review_result": "PASS\nReason: ok"}}


def test_run_agent_on_issue_ignores_none_node_outputs(monkeypatch, tmp_path):
    import autopatch

    monkeypatch.setattr(autopatch, "app", _FakeAppWithNoneNode())

    result = run_agent_on_issue(
        issue_text="Fix the calculator",
        working_dir=str(tmp_path),
        repo_language="Python",
    )

    assert result["review_result"] == "PASS\nReason: ok"
    assert result["step_count"] == 3


def test_extract_text_handles_anthropic_content_blocks():
    from agent.graph import _extract_text

    content = [
        {"type": "text", "text": "Line one"},
        {"type": "tool_use", "id": "tool-1", "name": "read_file"},
        {"type": "text", "text": "Line two"},
    ]

    assert _extract_text(content) == "Line one Line two"


def test_planner_node_accepts_list_content_blocks(monkeypatch):
    from langchain_core.messages import AIMessage
    from agent import graph

    class _FakePlanner:
        def invoke(self, messages):
            return AIMessage(content=[{"type": "text", "text": "### Execution Plan\n1. Fix calculator"}])

    monkeypatch.setattr(graph, "_llm_planner", _FakePlanner())

    result = graph.planner_node(
        {
            "messages": [],
            "issue_task": "Fix calculator",
            "repo_language": "Python",
            "plan": "",
            "test_output": "",
            "review_result": "",
            "review_retries": 0,
            "coder_steps": 0,
        }
    )

    assert result["plan"] == "### Execution Plan\n1. Fix calculator"


def test_index_builder_node_skips_when_rag_is_disabled(monkeypatch, tmp_path):
    from agent import graph
    from tools.workspace import reset_workspace, set_workspace

    calls = []

    class _FakeChunker:
        def chunk_directory(self, repo_path):
            calls.append(repo_path)
            return []

    monkeypatch.setattr(graph, "AUTOPATCH_RAG_ENABLED", False, raising=False)
    monkeypatch.setattr(graph, "_RAG_AVAILABLE", True)
    monkeypatch.setattr("src.rag.chunker.CodeChunker", _FakeChunker)

    token = set_workspace(str(tmp_path))
    try:
        result = graph.index_builder_node(
            {
                "messages": [],
                "issue_task": "Fix calculator",
                "repo_language": "Python",
                "plan": "",
                "test_output": "",
                "review_result": "",
                "review_retries": 0,
                "coder_steps": 0,
            }
        )
    finally:
        reset_workspace(token)

    assert result == {}
    assert calls == []
