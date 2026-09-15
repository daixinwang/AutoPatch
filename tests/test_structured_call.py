import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage

from agent.models import ExecutionPlan
from agent.next_nodes import structured_call

VALID = {"summary": "Fix discount", "steps": [{"id": "1", "objective": "Divide percent by 100"}]}


class Model:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.requests = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.requests.append(list(messages))
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.parametrize("invalid", [None, {"summary": "missing steps"}, OutputParserException("bad JSON")])
def test_invalid_structure_regenerated_without_mutating_history(invalid):
    model = Model([invalid, VALID])
    history = [HumanMessage(content="Fix discount")]
    assert structured_call(model, ExecutionPlan, history).summary == "Fix discount"
    assert len(model.requests) == 2
    assert len(history) == 1
    assert "ExecutionPlan" in model.requests[0][-1].content
    assert "JSON" in model.requests[1][-1].content
    assert all(message.type == "human" for message in model.requests[1])


def test_invalid_structure_stops_after_three_attempts():
    model = Model([None, None, None, VALID])
    with pytest.raises(ValueError, match="ExecutionPlan.*3 attempts"):
        structured_call(model, ExecutionPlan, [HumanMessage(content="Fix")])
    assert len(model.requests) == 3


def test_transport_errors_are_not_format_retries():
    model = Model([ConnectionError("offline"), VALID])
    with pytest.raises(ConnectionError):
        structured_call(model, ExecutionPlan, [HumanMessage(content="Fix")])
    assert len(model.requests) == 1
