def test_failure_dataset_has_five_cases():
    from eval.unified import build_parser, resolve_cases

    args = build_parser().parse_args(["--dataset", "sanity-v3", "--mode", "agent"])
    cases = resolve_cases(args)
    assert len(cases) >= 5
    assert {case.raw["recovery_scenario"] for case in cases} >= {
        "test_selection_error",
        "wrong_plan",
        "implementation_error",
        "environment_error",
        "unrecoverable",
    }


def test_ablation_cli():
    from eval.unified import build_parser

    args = build_parser().parse_args(["--dataset", "sanity-v3", "--mode", "scripted", "--ablation", "no_replanner"])
    assert args.ablation == "no_replanner"


def test_model_authentication_failure_is_infrastructure(tmp_path, monkeypatch):
    from pathlib import Path

    import anthropic
    import httpx

    import autopatch
    from eval.unified_models import PreparedWorkspace
    from eval.unified_providers import LocalSanityProvider
    from eval.unified_runner import UnifiedEvalRunner

    cases = LocalSanityProvider("sanity-v1", Path("eval/cases/sanity-v1")).load()
    case = next(case for case in cases if case.case_id == "py-single-file")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def denied(**kwargs):
        raise anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=request), body={})

    monkeypatch.setattr(autopatch, "run_agent_on_issue", denied)
    runner = UnifiedEvalRunner([case], "auth-test", tmp_path, "agent")
    directory = tmp_path / "case"
    directory.mkdir()
    result = runner._apply_and_validate(case, PreparedWorkspace(tmp_path, "base"), directory, directory / "trace.jsonl")
    assert result["verdict"] == "infra_error"
    assert result["failure_category"] == "model_service_error"
