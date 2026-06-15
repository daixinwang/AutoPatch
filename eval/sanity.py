"""
eval/sanity.py
--------------
Local sanity benchmark helpers.

This module intentionally covers only the first evaluation step: preparing a
workspace from a local fixture and running baseline validation. It does not run
the AutoPatch agent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class SanityBaselineResult:
    case_id: str
    verdict: str
    result_dir: Path
    workspace: Path
    base_commit: str


AgentRunner = Callable[[str, str, str], dict[str, Any]]


def run_dataset_baseline_only(
    cases_dir: Path = Path("eval/cases/sanity-v1"),
    results_dir: Path = Path("eval/results"),
    run_id: str | None = None,
) -> list[SanityBaselineResult]:
    """Run baseline validation for every case JSON in a sanity dataset."""
    project_root = Path(__file__).resolve().parents[1]
    dataset_dir = _resolve_from_root(project_root, cases_dir)
    run = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_sanity")
    run_dir = _resolve_from_root(project_root, results_dir) / run
    run_dir.mkdir(parents=True, exist_ok=True)

    case_files = sorted(dataset_dir.glob("*.json"))
    results = [
        run_baseline_only(case_file=case_file, results_dir=results_dir, run_id=run)
        for case_file in case_files
    ]

    counts = _count_verdicts(results)
    config = {
        "protocol_version": "2026-06-14",
        "run_id": run,
        "autopatch_commit": _git_output(project_root, ["git", "rev-parse", "HEAD"]),
        "autopatch_dirty": bool(_git_output(project_root, ["git", "status", "--short"])),
        "dataset_name": dataset_dir.name,
        "dataset_version": "2026-06-14",
        "case_ids": [result.case_id for result in results],
        "agent_config": {
            "mode": "baseline_only",
            "rag_enabled": None,
            "reviewer_enabled": None,
        },
        "environment": {
            "python_version": sys.version.split()[0],
            "docker_enabled": False,
        },
    }
    report = {
        "run_id": run,
        "dataset_name": dataset_dir.name,
        "total_cases": len(results),
        "baseline_ready": counts.get("baseline_ready", 0),
        "invalid_case": counts.get("invalid_case", 0),
        "infra_error": counts.get("infra_error", 0),
        "cases": [
            {
                "case_id": result.case_id,
                "verdict": result.verdict,
                "base_commit": result.base_commit,
            }
            for result in results
        ],
    }

    _write_json(run_dir / "config.json", config)
    _write_json(run_dir / "report.json", report)
    _write_report_md(run_dir / "report.md", report)
    return results


def run_dataset_with_mock_patches(
    cases_dir: Path = Path("eval/cases/sanity-v1"),
    patch_dir: Path = Path("eval/mock_patches/sanity-v1/resolved"),
    results_dir: Path = Path("eval/results"),
    run_id: str | None = None,
) -> list[SanityBaselineResult]:
    """Run all cases with fixed patch files from patch_dir."""
    project_root = Path(__file__).resolve().parents[1]
    dataset_dir = _resolve_from_root(project_root, cases_dir)
    patches = _resolve_from_root(project_root, patch_dir)
    run = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_sanity_mock")
    run_dir = _resolve_from_root(project_root, results_dir) / run
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[SanityBaselineResult] = []
    for case_file in sorted(dataset_dir.glob("*.json")):
        case = _load_json(case_file)
        patch_file = patches / f"{case['case_id']}.diff"
        if patch_file.exists():
            result = run_with_mock_patch(
                case_file=case_file,
                patch_file=patch_file,
                results_dir=results_dir,
                run_id=run,
            )
        else:
            result = run_baseline_only(case_file=case_file, results_dir=results_dir, run_id=run)
            if result.verdict == "baseline_ready":
                _write_final_verdict(
                    result.result_dir,
                    case_id=result.case_id,
                    verdict="failed",
                    reason=f"Mock patch file not found: {patch_file}",
                    patch_applies=False,
                    modified_test_files=False,
                    failure_category="patch_apply_failure",
                    fail_to_pass={},
                    pass_to_pass={},
                )
                result.verdict = "failed"
        results.append(result)

    counts = _count_verdicts(results)
    config = {
        "protocol_version": "2026-06-14",
        "run_id": run,
        "autopatch_commit": _git_output(project_root, ["git", "rev-parse", "HEAD"]),
        "autopatch_dirty": bool(_git_output(project_root, ["git", "status", "--short"])),
        "dataset_name": dataset_dir.name,
        "dataset_version": "2026-06-14",
        "case_ids": [result.case_id for result in results],
        "mock_patch_dir": str(patch_dir),
        "agent_config": {
            "mode": "mock_patch",
            "rag_enabled": None,
            "reviewer_enabled": None,
        },
        "environment": {
            "python_version": sys.version.split()[0],
            "docker_enabled": False,
        },
    }
    report = {
        "run_id": run,
        "dataset_name": dataset_dir.name,
        "total_cases": len(results),
        "resolved": counts.get("resolved", 0),
        "partial": counts.get("partial", 0),
        "failed": counts.get("failed", 0),
        "invalid_case": counts.get("invalid_case", 0),
        "infra_error": counts.get("infra_error", 0),
        "cases": [
            {
                "case_id": result.case_id,
                "verdict": result.verdict,
                "base_commit": result.base_commit,
            }
            for result in results
        ],
    }

    _write_json(run_dir / "config.json", config)
    _write_json(run_dir / "report.json", report)
    _write_report_md(run_dir / "report.md", report)
    return results


def run_dataset_with_agent(
    cases_dir: Path = Path("eval/cases/sanity-v1"),
    results_dir: Path = Path("eval/results"),
    run_id: str | None = None,
    case_ids: list[str] | None = None,
    agent_runner: AgentRunner | None = None,
) -> list[SanityBaselineResult]:
    """Run selected sanity cases through the real AutoPatch agent interface."""
    project_root = Path(__file__).resolve().parents[1]
    dataset_dir = _resolve_from_root(project_root, cases_dir)
    run = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_sanity_agent")
    run_dir = _resolve_from_root(project_root, results_dir) / run
    run_dir.mkdir(parents=True, exist_ok=True)

    selected = set(case_ids or [])
    case_files = [
        path for path in sorted(dataset_dir.glob("*.json"))
        if not selected or _load_json(path)["case_id"] in selected
    ]
    runner = agent_runner or _default_agent_runner
    results = [
        run_with_agent(
            case_file=case_file,
            results_dir=results_dir,
            run_id=run,
            agent_runner=runner,
        )
        for case_file in case_files
    ]

    counts = _count_verdicts(results)
    config = {
        "protocol_version": "2026-06-14",
        "run_id": run,
        "autopatch_commit": _git_output(project_root, ["git", "rev-parse", "HEAD"]),
        "autopatch_dirty": bool(_git_output(project_root, ["git", "status", "--short"])),
        "dataset_name": dataset_dir.name,
        "dataset_version": "2026-06-14",
        "case_ids": [result.case_id for result in results],
        "agent_config": {
            "mode": "agent",
            "rag_enabled": None,
            "reviewer_enabled": None,
        },
        "environment": {
            "python_version": sys.version.split()[0],
            "docker_enabled": False,
        },
    }
    report = {
        "run_id": run,
        "dataset_name": dataset_dir.name,
        "total_cases": len(results),
        "resolved": counts.get("resolved", 0),
        "partial": counts.get("partial", 0),
        "failed": counts.get("failed", 0),
        "invalid_case": counts.get("invalid_case", 0),
        "infra_error": counts.get("infra_error", 0),
        "cases": [
            {
                "case_id": result.case_id,
                "verdict": result.verdict,
                "base_commit": result.base_commit,
            }
            for result in results
        ],
    }

    _write_json(run_dir / "config.json", config)
    _write_json(run_dir / "report.json", report)
    _write_report_md(run_dir / "report.md", report)
    return results


def run_baseline_only(
    case_file: Path,
    results_dir: Path = Path("eval/results"),
    run_id: str | None = None,
) -> SanityBaselineResult:
    """Prepare one sanity case workspace and run baseline validation."""
    project_root = Path(__file__).resolve().parents[1]
    case_path = _resolve_from_root(project_root, case_file)
    case = _load_json(case_path)
    case_id = case["case_id"]
    run = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_sanity")

    case_dir = _resolve_from_root(project_root, results_dir) / run / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    workspace_root = _resolve_from_root(project_root, results_dir) / run / "workspaces"
    workspace = workspace_root / case_id
    if workspace.exists():
        shutil.rmtree(workspace)
    fixture_path = _resolve_from_root(project_root, Path(case["fixture_path"]))
    shutil.copytree(fixture_path, workspace)

    base_commit = _init_git_baseline(workspace)
    _write_case_artifacts(case_dir, case, workspace, base_commit)

    f2p = _run_selectors(workspace, case.get("fail_to_pass", []))
    p2p = _run_selectors(workspace, case.get("pass_to_pass", []))
    _write_test_before_log(case_dir, f2p, p2p)

    f2p_passed = [test_id for test_id, data in f2p.items() if data["passed"]]
    f2p_failed = [test_id for test_id, data in f2p.items() if not data["passed"]]
    p2p_passed = [test_id for test_id, data in p2p.items() if data["passed"]]
    p2p_failed = [test_id for test_id, data in p2p.items() if not data["passed"]]

    if f2p_passed:
        verdict = "invalid_case"
        reason = "FAIL_TO_PASS tests already pass before any patch; case metadata or baseline is invalid."
    elif p2p_failed:
        verdict = "infra_error"
        reason = "PASS_TO_PASS tests fail before any patch; baseline environment is not valid."
    else:
        verdict = "baseline_ready"
        reason = "Baseline is valid: FAIL_TO_PASS failed and PASS_TO_PASS passed before patch."

    verdict_data = {
        "case_id": case_id,
        "verdict": verdict,
        "reason": reason,
        "patch_applies": None,
        "modified_test_files": False,
        "fail_to_pass": {
            "total": len(f2p),
            "passed": len(f2p_passed),
            "failed": f2p_failed,
        },
        "pass_to_pass": {
            "total": len(p2p),
            "passed": len(p2p_passed),
            "failed": p2p_failed,
        },
        "timing": {
            "agent_seconds": None,
            "verification_seconds": None,
        },
    }
    _write_json(case_dir / "verdict.json", verdict_data)

    return SanityBaselineResult(
        case_id=case_id,
        verdict=verdict,
        result_dir=case_dir,
        workspace=workspace,
        base_commit=base_commit,
    )


def run_with_agent(
    case_file: Path,
    results_dir: Path = Path("eval/results"),
    run_id: str | None = None,
    agent_runner: AgentRunner | None = None,
) -> SanityBaselineResult:
    """Run baseline validation, invoke AutoPatch agent, then classify its workspace diff."""
    result = run_baseline_only(case_file=case_file, results_dir=results_dir, run_id=run_id)
    trace_path = result.result_dir / "trace.jsonl"
    _append_trace_event(trace_path, {"type": "case_started", "case_id": result.case_id})

    if result.verdict != "baseline_ready":
        _append_trace_event(trace_path, {"type": "case_finished", "case_id": result.case_id, "verdict": result.verdict})
        return result

    case = _load_json(result.result_dir / "case.json")
    runner = agent_runner or _default_agent_runner
    issue_text = (result.result_dir / "issue.md").read_text(encoding="utf-8")
    _append_trace_event(trace_path, {"type": "agent_started", "case_id": result.case_id})
    try:
        agent_result = runner(issue_text, str(result.workspace), case.get("language", "Unknown"))
    except Exception as exc:
        _write_json(result.result_dir / "changed-files.json", [])
        _write_final_verdict(
            result.result_dir,
            case_id=result.case_id,
            verdict="failed",
            reason=f"Agent execution failed: {type(exc).__name__}: {exc}",
            patch_applies=False,
            modified_test_files=False,
            failure_category="tool_failure",
            fail_to_pass={},
            pass_to_pass={},
        )
        result.verdict = "failed"
        _append_trace_event(trace_path, {"type": "agent_failed", "case_id": result.case_id, "error": str(exc)})
        _append_trace_event(trace_path, {"type": "case_finished", "case_id": result.case_id, "verdict": result.verdict})
        return result

    _append_trace_event(trace_path, {"type": "agent_finished", "case_id": result.case_id, "agent_result": agent_result})
    verdict = _validate_current_workspace_after_patch(result, case, agent_result=agent_result)
    result.verdict = verdict
    _append_trace_event(trace_path, {"type": "case_finished", "case_id": result.case_id, "verdict": result.verdict})
    return result


def run_with_mock_patch(
    case_file: Path,
    patch_file: Path,
    results_dir: Path = Path("eval/results"),
    run_id: str | None = None,
) -> SanityBaselineResult:
    """Run baseline validation, apply a fixed patch, then classify the final verdict."""
    project_root = Path(__file__).resolve().parents[1]
    patch_path = _resolve_from_root(project_root, patch_file)
    result = run_baseline_only(case_file=case_file, results_dir=results_dir, run_id=run_id)

    if result.verdict != "baseline_ready":
        return result

    case = _load_json(result.result_dir / "case.json")
    apply_result = subprocess.run(
        ["git", "apply", str(patch_path)],
        cwd=result.workspace,
        capture_output=True,
        text=True,
    )

    if apply_result.returncode != 0:
        (result.result_dir / "patch.diff").write_text(patch_path.read_text(encoding="utf-8"), encoding="utf-8")
        _write_json(result.result_dir / "changed-files.json", [])
        _write_final_verdict(
            result.result_dir,
            case_id=result.case_id,
            verdict="failed",
            reason=f"Patch did not apply cleanly: {apply_result.stderr.strip()}",
            patch_applies=False,
            modified_test_files=False,
            failure_category="patch_apply_failure",
            fail_to_pass={},
            pass_to_pass={},
        )
        result.verdict = "failed"
        return result

    verdict = _validate_current_workspace_after_patch(result, case)
    result.verdict = verdict
    return result


def _validate_current_workspace_after_patch(
    result: SanityBaselineResult,
    case: dict[str, Any],
    agent_result: dict[str, Any] | None = None,
) -> str:
    patch_diff = _git_output(result.workspace, ["git", "diff", "HEAD"])
    (result.result_dir / "patch.diff").write_text(patch_diff + ("\n" if patch_diff else ""), encoding="utf-8")

    changed_files = _get_changed_files(result.workspace)
    _write_json(result.result_dir / "changed-files.json", changed_files)
    modified_test_files = any(item["is_test"] for item in changed_files)

    if not patch_diff.strip():
        _write_final_verdict(
            result.result_dir,
            case_id=result.case_id,
            verdict="failed",
            reason="No patch was produced.",
            patch_applies=False,
            modified_test_files=False,
            failure_category="wrong_fix",
            fail_to_pass={},
            pass_to_pass={},
            extra={"agent_result": agent_result} if agent_result is not None else None,
        )
        return "failed"

    if modified_test_files and not case.get("allow_test_modifications", False):
        _write_final_verdict(
            result.result_dir,
            case_id=result.case_id,
            verdict="failed",
            reason="Patch modified test files, which is prohibited for this benchmark.",
            patch_applies=True,
            modified_test_files=True,
            failure_category="test_modification",
            fail_to_pass={},
            pass_to_pass={},
            extra={"agent_result": agent_result} if agent_result is not None else None,
        )
        return "failed"

    f2p = _run_selectors(result.workspace, case.get("fail_to_pass", []))
    p2p = _run_selectors(result.workspace, case.get("pass_to_pass", []))
    _write_test_log(result.result_dir / "test-after.log", "Patch Validation", f2p, p2p)

    f2p_passed = [test_id for test_id, data in f2p.items() if data["passed"]]
    f2p_failed = [test_id for test_id, data in f2p.items() if not data["passed"]]
    p2p_failed = [test_id for test_id, data in p2p.items() if not data["passed"]]

    if f2p_failed:
        verdict = "failed"
        reason = "At least one FAIL_TO_PASS test still fails after patch."
        failure_category = "incomplete_fix"
    elif p2p_failed:
        verdict = "partial"
        reason = "FAIL_TO_PASS passed, but at least one PASS_TO_PASS test failed after patch."
        failure_category = "regression"
    else:
        verdict = "resolved"
        reason = "FAIL_TO_PASS and PASS_TO_PASS passed after patch."
        failure_category = None

    _write_final_verdict(
        result.result_dir,
        case_id=result.case_id,
        verdict=verdict,
        reason=reason,
        patch_applies=True,
        modified_test_files=False,
        failure_category=failure_category,
        fail_to_pass=f2p,
        pass_to_pass=p2p,
        extra={"agent_result": agent_result} if agent_result is not None else None,
    )
    return verdict


def _count_verdicts(results: list[SanityBaselineResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    return counts


def _default_agent_runner(issue_text: str, working_dir: str, repo_language: str) -> dict[str, Any]:
    from autopatch import run_agent_on_issue

    return run_agent_on_issue(
        issue_text=issue_text,
        working_dir=working_dir,
        repo_language=repo_language,
    )


def _append_trace_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _git_output(cwd: Path, cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _get_changed_files(workspace: Path) -> list[dict[str, Any]]:
    output = _git_output(workspace, ["git", "diff", "--name-status", "HEAD"])
    files: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        files.append(
            {
                "path": path,
                "is_test": _is_test_path(path),
                "change_type": _change_type(status),
            }
        )
    return files


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    basename = Path(path).name
    return (
        any(part in {"tests", "test", "spec", "__tests__"} for part in parts)
        or basename.startswith("test_")
        or basename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _change_type(status: str) -> str:
    if status.startswith("A"):
        return "added"
    if status.startswith("D"):
        return "deleted"
    if status.startswith("R"):
        return "renamed"
    return "modified"


def _resolve_from_root(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _init_git_baseline(workspace: Path) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "AutoPatch Sanity",
        "GIT_AUTHOR_EMAIL": "autopatch-sanity@example.local",
        "GIT_COMMITTER_NAME": "AutoPatch Sanity",
        "GIT_COMMITTER_EMAIL": "autopatch-sanity@example.local",
    }
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True, env=env)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True, env=env)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True, text=True, env=env)
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _write_case_artifacts(case_dir: Path, case: dict[str, Any], workspace: Path, base_commit: str) -> None:
    _write_json(case_dir / "case.json", case)
    issue_text = f"# {case['issue_title']}\n\n{case['issue_body']}\n"
    (case_dir / "issue.md").write_text(issue_text, encoding="utf-8")
    _write_json(
        case_dir / "workspace-info.json",
        {
            "workspace": str(workspace),
            "base_commit": base_commit,
            "base_commit_strategy": case.get("base_commit_strategy"),
            "fixture_path": case.get("fixture_path"),
        },
    )


def _run_selectors(workspace: Path, selectors: list[str]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for selector in selectors:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", selector],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )
        results[selector] = {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    return results


def _write_test_before_log(
    case_dir: Path,
    fail_to_pass: dict[str, dict[str, Any]],
    pass_to_pass: dict[str, dict[str, Any]],
) -> None:
    _write_test_log(case_dir / "test-before.log", "Baseline Validation", fail_to_pass, pass_to_pass)


def _write_test_log(
    path: Path,
    title: str,
    fail_to_pass: dict[str, dict[str, Any]],
    pass_to_pass: dict[str, dict[str, Any]],
) -> None:
    lines = [f"# {title}", ""]
    for group_name, results in (("FAIL_TO_PASS", fail_to_pass), ("PASS_TO_PASS", pass_to_pass)):
        lines.append(f"## {group_name}")
        lines.append("")
        for selector, data in results.items():
            status = "PASSED" if data["passed"] else "FAILED"
            lines.append(f"### {selector}")
            lines.append(f"Status: {status} (exit {data['returncode']})")
            if data["stdout"].strip():
                lines.append("")
                lines.append("stdout:")
                lines.append("```")
                lines.append(data["stdout"].rstrip())
                lines.append("```")
            if data["stderr"].strip():
                lines.append("")
                lines.append("stderr:")
                lines.append("```")
                lines.append(data["stderr"].rstrip())
                lines.append("```")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_final_verdict(
    case_dir: Path,
    case_id: str,
    verdict: str,
    reason: str,
    patch_applies: bool,
    modified_test_files: bool,
    failure_category: str | None,
    fail_to_pass: dict[str, dict[str, Any]],
    pass_to_pass: dict[str, dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> None:
    f2p_passed = [test_id for test_id, data in fail_to_pass.items() if data["passed"]]
    f2p_failed = [test_id for test_id, data in fail_to_pass.items() if not data["passed"]]
    p2p_passed = [test_id for test_id, data in pass_to_pass.items() if data["passed"]]
    p2p_failed = [test_id for test_id, data in pass_to_pass.items() if not data["passed"]]

    data: dict[str, Any] = {
        "case_id": case_id,
        "verdict": verdict,
        "reason": reason,
        "patch_applies": patch_applies,
        "modified_test_files": modified_test_files,
        "fail_to_pass": {
            "total": len(fail_to_pass),
            "passed": len(f2p_passed),
            "failed": f2p_failed,
        },
        "pass_to_pass": {
            "total": len(pass_to_pass),
            "passed": len(p2p_passed),
            "failed": p2p_failed,
        },
        "timing": {
            "agent_seconds": None,
            "verification_seconds": None,
        },
    }
    if extra:
        data.update(extra)
    if failure_category is not None:
        data["failure_category"] = failure_category
    _write_json(case_dir / "verdict.json", data)


def _write_report_md(path: Path, report: dict[str, Any]) -> None:
    summary_keys = [
        ("Total cases", "total_cases"),
        ("Baseline ready", "baseline_ready"),
        ("Resolved", "resolved"),
        ("Partial", "partial"),
        ("Failed", "failed"),
        ("Invalid case", "invalid_case"),
        ("Infra error", "infra_error"),
    ]
    lines = [
        f"# {report['dataset_name']} Report",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Dataset: `{report['dataset_name']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for label, key in summary_keys:
        if key in report:
            lines.append(f"| {label} | {report[key]} |")
    lines += [
        "",
        "## Cases",
        "",
        "| Case | Verdict | Base commit |",
        "|---|---|---|",
    ]
    for case in report["cases"]:
        lines.append(f"| `{case['case_id']}` | `{case['verdict']}` | `{case['base_commit']}` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local AutoPatch sanity benchmarks.")
    parser.add_argument("--cases-dir", default="eval/cases/sanity-v1")
    parser.add_argument("--results-dir", default="eval/results")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--case-ids", nargs="+", default=None)
    parser.add_argument("--baseline-only", action="store_true", help="Run baseline validation only.")
    parser.add_argument("--mock-patch-dir", default=None, help="Apply fixed patches from this directory.")
    parser.add_argument("--agent", action="store_true", help="Run the real AutoPatch agent.")
    args = parser.parse_args(argv)

    modes = [args.baseline_only, bool(args.mock_patch_dir), args.agent]
    if sum(1 for enabled in modes if enabled) != 1:
        parser.error("Pass exactly one of --baseline-only, --mock-patch-dir, or --agent.")

    if args.mock_patch_dir:
        run_dataset_with_mock_patches(
            cases_dir=Path(args.cases_dir),
            patch_dir=Path(args.mock_patch_dir),
            results_dir=Path(args.results_dir),
            run_id=args.run_id,
        )
        return 0

    if args.agent:
        run_dataset_with_agent(
            cases_dir=Path(args.cases_dir),
            results_dir=Path(args.results_dir),
            run_id=args.run_id,
            case_ids=args.case_ids,
        )
        return 0

    run_dataset_baseline_only(
        cases_dir=Path(args.cases_dir),
        results_dir=Path(args.results_dir),
        run_id=args.run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
