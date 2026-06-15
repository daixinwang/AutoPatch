from __future__ import annotations

import json
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from core.diff_generator import filter_diff, generate_diff
from eval.config import EvalConfig
from eval.unified_models import PreparedWorkspace, UnifiedCase, classify_changed_file
from eval.unified_preparers import LocalFixturePreparer, SWEBenchPreparer


EvalMode = Literal["baseline-only", "mock-patch", "agent"]


class UnifiedEvalRunner:
    def __init__(
        self,
        cases: List[UnifiedCase],
        run_id: str,
        results_dir: Path,
        mode: EvalMode,
        mock_patch_dir: Optional[Path] = None,
        eval_config: Optional[EvalConfig] = None,
    ):
        self.cases = cases
        self.run_id = run_id
        self.results_dir = Path(results_dir)
        self.mode = mode
        self.mock_patch_dir = mock_patch_dir
        self.eval_config = eval_config or EvalConfig(results_dir=str(self.results_dir), timeout_per_instance=30)
        self.project_root = Path(__file__).resolve().parents[1]
        self.run_dir = self.results_dir / self.run_id
        self.selector_timeout_seconds = max(1, self.eval_config.timeout_per_instance // 2)
        self.case_timeout_seconds = max(1, self.eval_config.timeout_per_instance)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        case_reports: List[Dict[str, Any]] = []
        counts = {
            "baseline_ready": 0,
            "resolved": 0,
            "partial": 0,
            "failed": 0,
            "agent_timeout": 0,
            "invalid_case": 0,
            "infra_error": 0,
        }

        for case in self.cases:
            outcome = self._run_case(case)
            case_reports.append(outcome)
            counts[outcome["verdict"]] = counts.get(outcome["verdict"], 0) + 1

        report: Dict[str, Any] = {
            "protocol_version": "2026-06-14",
            "run_id": self.run_id,
            "dataset_name": self.cases[0].dataset_name if self.cases else None,
            "mode": self.mode,
            "total_cases": len(self.cases),
            "baseline_ready": counts["baseline_ready"],
            "resolved": counts["resolved"],
            "partial": counts["partial"],
            "failed": counts["failed"],
            "agent_timeout": counts["agent_timeout"],
            "invalid_case": counts["invalid_case"],
            "infra_error": counts["infra_error"],
            "resolved_rate_all": self._resolved_rate_all(counts),
            "resolved_rate_valid": self._resolved_rate_valid(counts),
            "cases": case_reports,
        }

        autopatch_commit = self._git_output(self.project_root, ["git", "rev-parse", "HEAD"]) or None
        autopatch_dirty = bool(self._git_output(self.project_root, ["git", "status", "--short"]))
        config = {
            "protocol_version": "2026-06-14",
            "run_id": self.run_id,
            "dataset_name": self.cases[0].dataset_name if self.cases else None,
            "dataset_version": "2026-06-14",
            "autopatch_commit": autopatch_commit,
            "autopatch_dirty": autopatch_dirty,
            "mode": self.mode,
            "case_ids": [case.case_id for case in self.cases],
            "agent_config": {
                "mode": self.mode,
                "rag_enabled": None,
                "reviewer_enabled": None,
            },
            "environment": {
                "python_version": sys.version.split()[0],
                "docker_enabled": self.eval_config.use_docker,
            },
            "timeouts": {
                "test_seconds": self.selector_timeout_seconds,
                "case_seconds": self.case_timeout_seconds,
            },
        }
        if self.mock_patch_dir is not None:
            config["mock_patch_dir"] = str(self.mock_patch_dir)

        self._write_json(self.run_dir / "config.json", config)
        self._write_json(self.run_dir / "report.json", report)
        self._write_report_md(self.run_dir / "report.md", report)
        return report

    def _run_case(self, case: UnifiedCase) -> Dict[str, Any]:
        case_dir = self.run_dir / "cases" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        trace_path = case_dir / "trace.jsonl"
        self._append_trace_event(trace_path, {"type": "case_started", "case_id": case.case_id})

        prepared: Optional[PreparedWorkspace] = None
        verdict = "infra_error"
        failure_category: Optional[str] = None
        try:
            prepared = self._prepare_workspace(case)
            self._write_case_artifacts(case_dir, case, prepared)
            baseline = self._run_baseline(case, prepared, case_dir)
            verdict = baseline["verdict"]
            self._write_verdict(
                case_dir,
                case.case_id,
                verdict,
                baseline["reason"],
                False,
                False,
                baseline.get("failure_category"),
                {},
                {},
            )

            if verdict != "baseline_ready" or self.mode == "baseline-only":
                self._append_trace_event(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": verdict})
                return self._case_report(case, verdict, prepared.base_commit, failure_category)

            self._append_trace_event(trace_path, {"type": "validation_started", "case_id": case.case_id})
            patch_result = self._apply_and_validate(case, prepared, case_dir, trace_path)
            verdict = patch_result["verdict"]
            failure_category = patch_result.get("failure_category")
            self._append_trace_event(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": verdict})
            return self._case_report(case, verdict, prepared.base_commit, failure_category)
        except TimeoutError as exc:
            self._write_changed_files(case_dir, [])
            self._write_patch_diff(case_dir, "")
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                f"Agent execution timed out: {exc}",
                False,
                False,
                "timeout",
                {},
                {},
            )
            self._append_trace_event(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": "failed"})
            return self._case_report(case, "failed", prepared.base_commit if prepared else None, "timeout")
        except Exception as exc:
            self._write_changed_files(case_dir, [])
            self._write_patch_diff(case_dir, "")
            self._write_verdict(
                case_dir,
                case.case_id,
                "infra_error",
                f"{type(exc).__name__}: {exc}",
                False,
                False,
                "tool_failure",
                {},
                {},
            )
            self._append_trace_event(trace_path, {
                "type": "case_finished",
                "case_id": case.case_id,
                "verdict": "infra_error",
                "error": traceback.format_exc(),
            })
            return self._case_report(case, "infra_error", prepared.base_commit if prepared else None, "tool_failure")
        finally:
            if prepared and prepared.cleanup is not None:
                try:
                    prepared.cleanup()
                except Exception:
                    pass

    def _prepare_workspace(self, case: UnifiedCase) -> PreparedWorkspace:
        if case.workspace_strategy == "swebench_instance":
            return SWEBenchPreparer(self.eval_config).prepare(case)
        return LocalFixturePreparer(self.run_dir).prepare(case)

    def _run_baseline(
        self,
        case: UnifiedCase,
        prepared: PreparedWorkspace,
        case_dir: Path,
    ) -> Dict[str, Any]:
        f2p = self._run_selectors(prepared.workspace, case.fail_to_pass)
        p2p = self._run_selectors(prepared.workspace, case.pass_to_pass)
        self._write_test_log(case_dir / "test-before.log", "Baseline Validation", f2p, p2p)

        if any(item["timed_out"] for item in f2p.values()) or any(item["timed_out"] for item in p2p.values()):
            return {
                "verdict": "infra_error",
                "reason": "Baseline test execution timed out.",
                "failure_category": "timeout",
            }

        if any(item["passed"] for item in f2p.values()):
            return {
                "verdict": "invalid_case",
                "reason": "FAIL_TO_PASS tests already pass before any patch; case metadata or baseline is invalid.",
            }

        if any(not item["passed"] for item in p2p.values()):
            return {
                "verdict": "infra_error",
                "reason": "PASS_TO_PASS tests fail before any patch; baseline environment is not valid.",
            }

        return {
            "verdict": "baseline_ready",
            "reason": "Baseline is valid: FAIL_TO_PASS failed and PASS_TO_PASS passed before patch.",
        }

    def _apply_and_validate(
        self,
        case: UnifiedCase,
        prepared: PreparedWorkspace,
        case_dir: Path,
        trace_path: Path,
    ) -> Dict[str, Any]:
        if self.mode == "mock-patch":
            return self._apply_mock_patch(case, prepared, case_dir)

        self._append_trace_event(trace_path, {"type": "agent_started", "case_id": case.case_id})
        from autopatch import run_agent_on_issue

        try:
            run_agent_on_issue(
                issue_text=case.issue_markdown(),
                working_dir=str(prepared.workspace),
                repo_language=case.language,
            )
        except TimeoutError:
            self._append_trace_event(trace_path, {"type": "agent_finished", "case_id": case.case_id, "status": "timeout"})
            self._write_changed_files(case_dir, [])
            self._write_patch_diff(case_dir, "")
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                "Agent execution timed out.",
                False,
                False,
                "timeout",
                {},
                {},
            )
            return {"verdict": "failed", "failure_category": "timeout"}
        except Exception as exc:
            self._append_trace_event(trace_path, {"type": "agent_failed", "case_id": case.case_id, "error": str(exc)})
            self._write_changed_files(case_dir, [])
            self._write_patch_diff(case_dir, "")
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                f"Agent execution failed: {type(exc).__name__}: {exc}",
                False,
                False,
                "tool_failure",
                {},
                {},
            )
            self._append_trace_event(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": "failed"})
            return {"verdict": "failed", "failure_category": "tool_failure"}

        self._append_trace_event(trace_path, {"type": "agent_finished", "case_id": case.case_id, "status": "ok"})
        return self._validate_patch(case, prepared, case_dir)

    def _apply_mock_patch(
        self,
        case: UnifiedCase,
        prepared: PreparedWorkspace,
        case_dir: Path,
    ) -> Dict[str, Any]:
        patch_dir = self._resolve_mock_patch_dir()
        patch_path = patch_dir / (case.case_id + ".diff")
        if not patch_path.exists():
            self._write_changed_files(case_dir, [])
            self._write_patch_diff(case_dir, "")
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                "Mock patch file not found.",
                False,
                False,
                "patch_apply_failure",
                {},
                {},
            )
            return {"verdict": "failed", "failure_category": "patch_apply_failure"}

        apply_result = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=prepared.workspace,
            capture_output=True,
            text=True,
        )
        if apply_result.returncode != 0:
            self._write_changed_files(case_dir, [])
            self._write_patch_diff(case_dir, patch_path.read_text(encoding="utf-8"))
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                f"Patch did not apply cleanly: {apply_result.stderr.strip()}",
                False,
                False,
                "patch_apply_failure",
                {},
                {},
            )
            return {"verdict": "failed", "failure_category": "patch_apply_failure"}

        return self._validate_patch(case, prepared, case_dir)

    def _validate_patch(self, case: UnifiedCase, prepared: PreparedWorkspace, case_dir: Path) -> Dict[str, Any]:
        raw_diff = generate_diff(prepared.workspace)
        patch_diff = filter_diff(raw_diff, prepared.test_patch_files) if prepared.test_patch_files else raw_diff
        self._write_patch_diff(case_dir, patch_diff)

        changed_files = self._changed_files(prepared.workspace, prepared.test_patch_files)
        self._write_changed_files(case_dir, changed_files)
        modified_test_files = any(item["is_test"] for item in changed_files)

        if not patch_diff.strip():
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                "No patch was produced.",
                False,
                False,
                "wrong_fix",
                {},
                {},
            )
            return {"verdict": "failed", "failure_category": "wrong_fix"}

        if modified_test_files and not case.allow_test_modifications:
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                "Patch modified test files, which is prohibited for this benchmark.",
                True,
                True,
                "test_modification",
                {},
                {},
            )
            return {"verdict": "failed", "failure_category": "test_modification"}

        f2p = self._run_selectors(prepared.workspace, case.fail_to_pass)
        p2p = self._run_selectors(prepared.workspace, case.pass_to_pass)
        self._write_test_log(case_dir / "test-after.log", "Patch Validation", f2p, p2p)

        if any(item["timed_out"] for item in f2p.values()) or any(item["timed_out"] for item in p2p.values()):
            self._write_verdict(
                case_dir,
                case.case_id,
                "failed",
                "Patch validation timed out.",
                True,
                False,
                "timeout",
                f2p,
                p2p,
            )
            return {"verdict": "failed", "failure_category": "timeout"}

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

        self._write_verdict(
            case_dir,
            case.case_id,
            verdict,
            reason,
            True,
            False,
            failure_category,
            f2p,
            p2p,
        )
        return {"verdict": verdict, "failure_category": failure_category}

    def _run_selectors(self, workspace: Path, selectors: List[str]) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for selector in selectors:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", selector],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=self.selector_timeout_seconds,
                )
                results[selector] = {
                    "passed": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "timed_out": False,
                }
            except subprocess.TimeoutExpired as exc:
                results[selector] = {
                    "passed": False,
                    "returncode": -1,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "timed_out": True,
                }
        return results

    def _changed_files(self, workspace: Path, exclude_paths: set) -> List[Dict[str, Any]]:
        result = subprocess.run(
            ["git", "diff", "--name-status", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        changed: List[Dict[str, Any]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            path = parts[-1]
            if path in exclude_paths:
                continue
            changed_file = classify_changed_file(status, path)
            changed.append(
                {
                    "path": changed_file.path,
                    "is_test": changed_file.is_test,
                    "change_type": changed_file.change_type,
                }
            )
        return changed

    def _write_case_artifacts(self, case_dir: Path, case: UnifiedCase, prepared: PreparedWorkspace) -> None:
        self._write_json(case_dir / "case.json", case.to_case_json())
        (case_dir / "issue.md").write_text(case.issue_markdown(), encoding="utf-8")
        self._write_json(
            case_dir / "workspace-info.json",
            {
                "workspace": str(prepared.workspace),
                "base_commit": prepared.base_commit,
                "workspace_strategy": case.workspace_strategy,
                "fixture_path": str(case.fixture_path) if case.fixture_path else None,
                "test_patch_files": sorted(prepared.test_patch_files),
            },
        )

    def _write_verdict(
        self,
        case_dir: Path,
        case_id: str,
        verdict: str,
        reason: str,
        patch_applies: bool,
        modified_test_files: bool,
        failure_category: Optional[str],
        fail_to_pass: Dict[str, Dict[str, Any]],
        pass_to_pass: Dict[str, Dict[str, Any]],
    ) -> None:
        f2p_passed = [test_id for test_id, data in fail_to_pass.items() if data.get("passed")]
        f2p_failed = [test_id for test_id, data in fail_to_pass.items() if not data.get("passed")]
        p2p_passed = [test_id for test_id, data in pass_to_pass.items() if data.get("passed")]
        p2p_failed = [test_id for test_id, data in pass_to_pass.items() if not data.get("passed")]

        payload: Dict[str, Any] = {
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
        if failure_category is not None:
            payload["failure_category"] = failure_category
        self._write_json(case_dir / "verdict.json", payload)

    def _write_patch_diff(self, case_dir: Path, patch_diff: str) -> None:
        text = patch_diff if patch_diff.endswith("\n") or not patch_diff else patch_diff + "\n"
        (case_dir / "patch.diff").write_text(text, encoding="utf-8")

    def _write_changed_files(self, case_dir: Path, changed_files: List[Dict[str, Any]]) -> None:
        self._write_json(case_dir / "changed-files.json", changed_files)

    def _write_test_log(
        self,
        path: Path,
        title: str,
        fail_to_pass: Dict[str, Dict[str, Any]],
        pass_to_pass: Dict[str, Dict[str, Any]],
    ) -> None:
        lines = [f"# {title}", ""]
        for group_name, results in (("FAIL_TO_PASS", fail_to_pass), ("PASS_TO_PASS", pass_to_pass)):
            lines.append(f"## {group_name}")
            lines.append("")
            for selector, data in results.items():
                if data.get("timed_out"):
                    status = "TIMEOUT"
                else:
                    status = "PASSED" if data.get("passed") else "FAILED"
                lines.append(f"### {selector}")
                lines.append(f"Status: {status} (exit {data.get('returncode')})")
                stdout = (data.get("stdout") or "").strip()
                stderr = (data.get("stderr") or "").strip()
                if stdout:
                    lines.append("")
                    lines.append("stdout:")
                    lines.append("```")
                    lines.append(stdout)
                    lines.append("```")
                if stderr:
                    lines.append("")
                    lines.append("stderr:")
                    lines.append("```")
                    lines.append(stderr)
                    lines.append("```")
                lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    def _case_report(
        self,
        case: UnifiedCase,
        verdict: str,
        base_commit: Optional[str],
        failure_category: Optional[str],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "case_id": case.case_id,
            "verdict": verdict,
            "base_commit": base_commit,
        }
        if failure_category is not None:
            payload["failure_category"] = failure_category
        return payload

    def _resolve_mock_patch_dir(self) -> Path:
        if self.mock_patch_dir is None:
            return self.project_root / "eval" / "mock_patches"
        if self.mock_patch_dir.is_absolute():
            return self.mock_patch_dir
        return self.project_root / self.mock_patch_dir

    def _git_output(self, cwd: Path, cmd: List[str]) -> str:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _resolved_rate_all(self, counts: Dict[str, int]) -> float:
        total = len(self.cases)
        if total == 0:
            return 0.0
        return float(counts.get("resolved", 0)) / float(total)

    def _resolved_rate_valid(self, counts: Dict[str, int]) -> float:
        valid = len(self.cases) - counts.get("invalid_case", 0) - counts.get("infra_error", 0)
        if valid <= 0:
            return 0.0
        return float(counts.get("resolved", 0)) / float(valid)

    def _append_trace_event(self, path: Path, event: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _write_report_md(self, path: Path, report: Dict[str, Any]) -> None:
        lines = [
            f"# {report.get('dataset_name') or 'unified'} Report",
            "",
            f"Run ID: `{report['run_id']}`",
            f"Mode: `{report['mode']}`",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
        for label, key in [
            ("Total cases", "total_cases"),
            ("Baseline ready", "baseline_ready"),
            ("Resolved", "resolved"),
            ("Partial", "partial"),
            ("Failed", "failed"),
            ("Agent timeout", "agent_timeout"),
            ("Invalid case", "invalid_case"),
            ("Infra error", "infra_error"),
        ]:
            lines.append(f"| {label} | {report.get(key, 0)} |")
        lines += [
            "",
            "## Cases",
            "",
            "| Case | Verdict | Base commit |",
            "|---|---|---|",
        ]
        for case in report["cases"]:
            lines.append(
                f"| `{case['case_id']}` | `{case['verdict']}` | `{case.get('base_commit') or ''}` |"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
