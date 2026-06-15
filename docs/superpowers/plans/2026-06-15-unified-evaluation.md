# Unified Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one evaluation runner that preserves `sanity-v1` and `sanity-v2` while adding pinned and dynamic SWE-bench case support under the same result protocol.

**Architecture:** Add a small unified evaluation layer around normalized case models, dataset providers, workspace preparers, and a shared case runner. Existing `eval.sanity`, `run_eval.py`, `InstanceEnvironment`, and `DockerEnvironment` remain available during migration; the unified code reuses stable pieces instead of deleting them.

**Tech Stack:** Python 3.10+, dataclasses, argparse, pytest, existing `eval.*` modules, optional HuggingFace `datasets`, optional Docker.

---

## File Structure

- Create `eval/unified_models.py`
  - Defines normalized dataclasses and constants shared by providers, preparers, runner, and tests.
- Create `eval/unified_providers.py`
  - Loads local sanity cases, dynamic SWE-bench cases, and pinned `swebench-smoke` cases into the normalized model.
- Create `eval/unified_preparers.py`
  - Prepares local fixture workspaces and adapts existing SWE-bench environment setup.
- Create `eval/unified_runner.py`
  - Runs baseline validation, mock patch mode, agent mode, patch validation, verdict writing, and aggregate reports.
- Create `eval/unified.py`
  - Provides the `python -m eval.unified` CLI.
- Create `tests/test_unified_models.py`
  - Covers verdict and changed-file helpers.
- Create `tests/test_unified_providers.py`
  - Covers sanity loading, SWE-bench local JSON loading, filtering, and smoke selection.
- Create `tests/test_unified_runner.py`
  - Covers baseline-only and mock-patch execution against existing sanity fixtures.
- Modify `docs/evaluation-protocol.md`
  - Add the unified CLI as the preferred runner without removing existing historical protocol text.
- Modify `README.md`
  - Add a short evaluation section pointing to unified commands.

---

### Task 1: Normalized Models And Helpers

**Files:**
- Create: `eval/unified_models.py`
- Test: `tests/test_unified_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_unified_models.py`:

```python
from pathlib import Path

from eval.unified_models import (
    ChangedFile,
    UnifiedCase,
    Verdict,
    classify_changed_file,
    is_test_path,
)


def test_is_test_path_detects_common_test_locations():
    assert is_test_path("tests/test_checkout.py")
    assert is_test_path("pkg/__tests__/widget.test.tsx")
    assert is_test_path("src/foo_test.py")
    assert not is_test_path("shop/pricing.py")


def test_classify_changed_file_maps_git_status():
    changed = classify_changed_file("M", "tests/test_checkout.py")

    assert changed == ChangedFile(
        path="tests/test_checkout.py",
        is_test=True,
        change_type="modified",
    )


def test_unified_case_issue_markdown_excludes_analysis_fields():
    case = UnifiedCase(
        case_id="py-single-file",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/sanity-py-single-file",
        base_commit=None,
        issue_title="Percentage discounts are 100x too large",
        issue_body="Fix the discount calculation.",
        language="Python",
        fail_to_pass=["tests/test_calculator.py::test_percentage_discount_uses_percent_units"],
        pass_to_pass=["tests/test_calculator.py::test_zero_discount_keeps_subtotal"],
        expected_files=["autopatch_demo/calculator.py"],
        allow_test_modifications=False,
        workspace_strategy="local_fixture",
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
        analysis_notes="Do not pass this to agent.",
        swebench_gold_patch="gold patch should stay hidden",
    )

    markdown = case.issue_markdown()

    assert markdown == "# Percentage discounts are 100x too large\n\nFix the discount calculation.\n"
    assert "gold patch" not in markdown
    assert "Do not pass" not in markdown


def test_verdict_values_match_protocol():
    assert [item.value for item in Verdict] == [
        "resolved",
        "partial",
        "failed",
        "agent_timeout",
        "infra_error",
        "invalid_case",
        "baseline_ready",
    ]
```

- [ ] **Step 2: Run model tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'eval.unified_models'`.

- [ ] **Step 3: Implement normalized models**

Create `eval/unified_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


WorkspaceStrategy = Literal["local_fixture", "swebench_instance"]


class Verdict(str, Enum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    FAILED = "failed"
    AGENT_TIMEOUT = "agent_timeout"
    INFRA_ERROR = "infra_error"
    INVALID_CASE = "invalid_case"
    BASELINE_READY = "baseline_ready"


@dataclass(frozen=True)
class ChangedFile:
    path: str
    is_test: bool
    change_type: str


@dataclass(frozen=True)
class UnifiedCase:
    case_id: str
    dataset_name: str
    source: str
    repo: str
    base_commit: str | None
    issue_title: str
    issue_body: str
    language: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    expected_files: list[str] = field(default_factory=list)
    allow_test_modifications: bool = False
    workspace_strategy: WorkspaceStrategy = "local_fixture"
    fixture_path: Path | None = None
    swebench_instance_id: str | None = None
    swebench_test_patch: str = ""
    swebench_gold_patch: str = ""
    environment_setup_commit: str | None = None
    version: str | None = None
    analysis_notes: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def issue_markdown(self) -> str:
        return f"# {self.issue_title}\n\n{self.issue_body}\n"

    def to_case_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "dataset_name": self.dataset_name,
            "source": self.source,
            "repo": self.repo,
            "base_commit": self.base_commit,
            "issue_title": self.issue_title,
            "issue_body": self.issue_body,
            "language": self.language,
            "fail_to_pass": self.fail_to_pass,
            "pass_to_pass": self.pass_to_pass,
            "expected_files": self.expected_files,
            "allow_test_modifications": self.allow_test_modifications,
            "workspace_strategy": self.workspace_strategy,
            "fixture_path": str(self.fixture_path) if self.fixture_path else None,
            "swebench_instance_id": self.swebench_instance_id,
            "environment_setup_commit": self.environment_setup_commit,
            "version": self.version,
        }


@dataclass(frozen=True)
class PreparedWorkspace:
    workspace: Path
    base_commit: str
    test_patch_files: set[str] = field(default_factory=set)
    cleanup: Any | None = None
    docker_container: str | None = None
    docker_container_path: str | None = None


def is_test_path(path: str) -> bool:
    parts = Path(path).parts
    basename = Path(path).name
    return (
        any(part in {"tests", "test", "spec", "__tests__"} for part in parts)
        or basename.startswith("test_")
        or basename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def classify_changed_file(status: str, path: str) -> ChangedFile:
    if status.startswith("A"):
        change_type = "added"
    elif status.startswith("D"):
        change_type = "deleted"
    elif status.startswith("R"):
        change_type = "renamed"
    else:
        change_type = "modified"
    return ChangedFile(path=path, is_test=is_test_path(path), change_type=change_type)
```

- [ ] **Step 4: Run model tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit task 1**

```bash
git add eval/unified_models.py tests/test_unified_models.py
git commit -m "feat: add unified evaluation models"
```

---

### Task 2: Dataset Providers

**Files:**
- Create: `eval/unified_providers.py`
- Test: `tests/test_unified_providers.py`

- [ ] **Step 1: Write failing provider tests**

Create `tests/test_unified_providers.py`:

```python
import json
from pathlib import Path

from eval.unified_providers import (
    DEFAULT_SWEBENCH_SMOKE_IDS,
    LocalSanityProvider,
    SWEBenchProvider,
    SWEBenchSmokeProvider,
)


def test_local_sanity_provider_loads_existing_case():
    provider = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    )

    cases = provider.load()
    case = next(item for item in cases if item.case_id == "py-single-file")

    assert len(cases) == 5
    assert case.dataset_name == "sanity-v1"
    assert case.workspace_strategy == "local_fixture"
    assert case.fixture_path == Path("eval/fixtures/sanity-v1/py-single-file")
    assert case.fail_to_pass == [
        "tests/test_calculator.py::test_percentage_discount_uses_percent_units"
    ]
    assert case.allow_test_modifications is False


def test_swebench_provider_loads_local_json_and_filters(tmp_path):
    data = [
        {
            "instance_id": "django__django-100",
            "repo": "django/django",
            "base_commit": "abc123",
            "problem_statement": "Fix query behavior.",
            "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n",
            "patch": "gold diff",
            "FAIL_TO_PASS": json.dumps(["tests.test_x.TestCase.test_bug"]),
            "PASS_TO_PASS": ["tests.test_x.TestCase.test_existing"],
            "version": "4.2",
            "environment_setup_commit": "env123",
        },
        {
            "instance_id": "sympy__sympy-200",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "problem_statement": "Fix simplify behavior.",
            "test_patch": "",
            "patch": "",
            "FAIL_TO_PASS": ["sympy/test_bug.py::test_bug"],
            "PASS_TO_PASS": [],
        },
    ]
    dataset = tmp_path / "swebench.json"
    dataset.write_text(json.dumps(data), encoding="utf-8")

    provider = SWEBenchProvider(
        dataset_name=str(dataset),
        dataset_split="test",
        instance_ids=["django__django-100"],
    )

    cases = provider.load()

    assert [case.case_id for case in cases] == ["django__django-100"]
    assert cases[0].dataset_name == "swebench-lite"
    assert cases[0].workspace_strategy == "swebench_instance"
    assert cases[0].issue_title == "SWE-bench issue django__django-100"
    assert cases[0].issue_body == "Fix query behavior."
    assert cases[0].swebench_gold_patch == "gold diff"
    assert cases[0].fail_to_pass == ["tests.test_x.TestCase.test_bug"]


def test_swebench_smoke_provider_uses_pinned_ids(tmp_path):
    data = []
    for instance_id in DEFAULT_SWEBENCH_SMOKE_IDS:
        data.append(
            {
                "instance_id": instance_id,
                "repo": "django/django",
                "base_commit": "abc123",
                "problem_statement": f"Problem for {instance_id}",
                "test_patch": "",
                "patch": "",
                "FAIL_TO_PASS": ["tests.test_x.TestCase.test_bug"],
                "PASS_TO_PASS": [],
            }
        )
    data.append(
        {
            "instance_id": "extra__case-1",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "problem_statement": "Extra problem.",
            "test_patch": "",
            "patch": "",
            "FAIL_TO_PASS": ["test_extra.py::test_bug"],
            "PASS_TO_PASS": [],
        }
    )
    dataset = tmp_path / "swebench.json"
    dataset.write_text(json.dumps(data), encoding="utf-8")

    provider = SWEBenchSmokeProvider(dataset_name=str(dataset), dataset_split="test")
    cases = provider.load()

    assert [case.case_id for case in cases] == DEFAULT_SWEBENCH_SMOKE_IDS
```

- [ ] **Step 2: Run provider tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_providers.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'eval.unified_providers'`.

- [ ] **Step 3: Implement providers**

Create `eval/unified_providers.py`:

```python
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from eval.dataset import _load_raw, _parse_item
from eval.unified_models import UnifiedCase


DEFAULT_SWEBENCH_SMOKE_IDS = [
    "pallets__flask-4045",
    "psf__requests-1963",
    "sympy__sympy-11400",
]


@dataclass(frozen=True)
class LocalSanityProvider:
    dataset_name: str
    cases_dir: Path

    def load(self) -> list[UnifiedCase]:
        cases: list[UnifiedCase] = []
        for path in sorted(self.cases_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            expected_files = data.get("expected_files", data.get("expected_modified_files", []))
            cases.append(
                UnifiedCase(
                    case_id=data["case_id"],
                    dataset_name=self.dataset_name,
                    source=data.get("source", "local_sanity"),
                    repo=data.get("repo", f"local/{data['case_id']}"),
                    base_commit=data.get("base_commit"),
                    issue_title=data["issue_title"],
                    issue_body=data["issue_body"],
                    language=data.get("language", "Python"),
                    fail_to_pass=list(data.get("fail_to_pass", [])),
                    pass_to_pass=list(data.get("pass_to_pass", [])),
                    expected_files=list(expected_files),
                    allow_test_modifications=bool(data.get("allow_test_modifications", False)),
                    workspace_strategy="local_fixture",
                    fixture_path=Path(data["fixture_path"]),
                    analysis_notes=data.get("notes"),
                    raw=data,
                )
            )
        return cases


@dataclass(frozen=True)
class SWEBenchProvider:
    dataset_name: str = "princeton-nlp/SWE-bench_Lite"
    dataset_split: str = "test"
    instance_ids: list[str] | None = None
    repos: list[str] | None = None
    max_instances: int | None = None
    shuffle: bool = False
    seed: int = 42

    def load(self) -> list[UnifiedCase]:
        raw_items = _load_raw(self.dataset_name, self.dataset_split)
        instances = [_parse_item(item) for item in raw_items]

        if self.instance_ids:
            wanted = set(self.instance_ids)
            instances = [item for item in instances if item.instance_id in wanted]
        if self.repos:
            wanted_repos = set(self.repos)
            instances = [item for item in instances if item.repo in wanted_repos]
        if self.shuffle:
            rng = random.Random(self.seed)
            rng.shuffle(instances)
        if self.max_instances is not None:
            instances = instances[: self.max_instances]

        return [
            UnifiedCase(
                case_id=item.instance_id,
                dataset_name="swebench-lite",
                source="swe_bench",
                repo=item.repo,
                base_commit=item.base_commit,
                issue_title=f"SWE-bench issue {item.instance_id}",
                issue_body=item.problem_statement,
                language="Python",
                fail_to_pass=item.fail_to_pass,
                pass_to_pass=item.pass_to_pass,
                expected_files=[],
                allow_test_modifications=False,
                workspace_strategy="swebench_instance",
                swebench_instance_id=item.instance_id,
                swebench_test_patch=item.test_patch,
                swebench_gold_patch=item.patch,
                environment_setup_commit=item.environment_setup_commit,
                version=item.version,
                raw=item.__dict__,
            )
            for item in instances
        ]


@dataclass(frozen=True)
class SWEBenchSmokeProvider:
    dataset_name: str = "princeton-nlp/SWE-bench_Lite"
    dataset_split: str = "test"
    smoke_ids: list[str] | None = None

    def load(self) -> list[UnifiedCase]:
        ids = self.smoke_ids or DEFAULT_SWEBENCH_SMOKE_IDS
        return SWEBenchProvider(
            dataset_name=self.dataset_name,
            dataset_split=self.dataset_split,
            instance_ids=ids,
        ).load()
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_providers.py tests/test_unified_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit task 2**

```bash
git add eval/unified_providers.py tests/test_unified_providers.py
git commit -m "feat: add unified evaluation providers"
```

---

### Task 3: Workspace Preparers

**Files:**
- Create: `eval/unified_preparers.py`
- Test: extend `tests/test_unified_runner.py` with preparer-focused tests

- [ ] **Step 1: Write failing preparer tests**

Create `tests/test_unified_runner.py` with the initial tests:

```python
from pathlib import Path

from eval.unified_models import UnifiedCase
from eval.unified_preparers import LocalFixturePreparer


def test_local_fixture_preparer_creates_git_baseline(tmp_path):
    case = UnifiedCase(
        case_id="py-single-file",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/sanity-py-single-file",
        base_commit=None,
        issue_title="Percentage discounts are 100x too large",
        issue_body="Fix the discount calculation.",
        language="Python",
        fail_to_pass=["tests/test_calculator.py::test_percentage_discount_uses_percent_units"],
        pass_to_pass=["tests/test_calculator.py::test_zero_discount_keeps_subtotal"],
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
    )

    prepared = LocalFixturePreparer(tmp_path).prepare(case)

    assert prepared.workspace == tmp_path / "workspaces" / "py-single-file"
    assert len(prepared.base_commit) == 40
    assert (prepared.workspace / ".git").exists()
    assert (prepared.workspace / "autopatch_demo" / "calculator.py").exists()
```

- [ ] **Step 2: Run preparer test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_runner.py::test_local_fixture_preparer_creates_git_baseline -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'eval.unified_preparers'`.

- [ ] **Step 3: Implement preparers**

Create `eval/unified_preparers.py`:

```python
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from eval.config import EvalConfig
from eval.dataset import SWEBenchInstance
from eval.instance_env import InstanceEnvironment
from eval.unified_models import PreparedWorkspace, UnifiedCase


class LocalFixturePreparer:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir

    def prepare(self, case: UnifiedCase) -> PreparedWorkspace:
        if case.fixture_path is None:
            raise ValueError(f"{case.case_id} has no fixture_path")
        workspace = self.run_dir / "workspaces" / case.case_id
        if workspace.exists():
            shutil.rmtree(workspace)
        fixture_path = case.fixture_path
        if not fixture_path.is_absolute():
            fixture_path = Path.cwd() / fixture_path
        shutil.copytree(fixture_path, workspace)
        base_commit = _init_git_baseline(workspace)
        return PreparedWorkspace(workspace=workspace, base_commit=base_commit)


class SWEBenchPreparer:
    def __init__(self, config: EvalConfig):
        self.config = config

    def prepare(self, case: UnifiedCase) -> PreparedWorkspace:
        instance = SWEBenchInstance(
            instance_id=case.swebench_instance_id or case.case_id,
            repo=case.repo,
            base_commit=case.base_commit or "",
            problem_statement=case.issue_body,
            test_patch=case.swebench_test_patch,
            patch=case.swebench_gold_patch,
            fail_to_pass=case.fail_to_pass,
            pass_to_pass=case.pass_to_pass,
            version=case.version,
            environment_setup_commit=case.environment_setup_commit,
        )
        if self.config.use_docker:
            from eval.docker_env import DockerEnvironment

            env = DockerEnvironment(instance, self.config)
        else:
            env = InstanceEnvironment(instance, self.config)
        workspace = env.setup()
        base_commit = _git_output(workspace, ["git", "rev-parse", "HEAD"]) or (case.base_commit or "")
        return PreparedWorkspace(
            workspace=workspace,
            base_commit=base_commit,
            test_patch_files=set(env.test_patch_files),
            cleanup=env.cleanup,
            docker_container=getattr(env, "container_name", None),
            docker_container_path=getattr(env, "_container_path", None),
        )


def _init_git_baseline(workspace: Path) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "AutoPatch Eval",
        "GIT_AUTHOR_EMAIL": "autopatch-eval@example.local",
        "GIT_COMMITTER_NAME": "AutoPatch Eval",
        "GIT_COMMITTER_EMAIL": "autopatch-eval@example.local",
    }
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True, env=env)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, text=True, env=env)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True, text=True, env=env)
    return _git_output(workspace, ["git", "rev-parse", "HEAD"])


def _git_output(cwd: Path, cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
```

- [ ] **Step 4: Run preparer test**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_runner.py::test_local_fixture_preparer_creates_git_baseline -q
```

Expected: PASS.

- [ ] **Step 5: Commit task 3**

```bash
git add eval/unified_preparers.py tests/test_unified_runner.py
git commit -m "feat: add unified evaluation preparers"
```

---

### Task 4: Unified Runner Core

**Files:**
- Create: `eval/unified_runner.py`
- Modify: `tests/test_unified_runner.py`

- [ ] **Step 1: Add failing runner tests**

Append to `tests/test_unified_runner.py`:

```python
import json

from eval.unified_providers import LocalSanityProvider
from eval.unified_runner import UnifiedEvalRunner


def test_unified_runner_baseline_only_writes_protocol_artifacts(tmp_path):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="baseline-run",
        results_dir=tmp_path,
        mode="baseline-only",
    )
    report = runner.run()

    case_dir = tmp_path / "baseline-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert report["baseline_ready"] == 1
    assert verdict["verdict"] == "baseline_ready"
    assert (case_dir / "case.json").exists()
    assert (case_dir / "issue.md").exists()
    assert (case_dir / "test-before.log").exists()
    assert (tmp_path / "baseline-run" / "report.json").exists()
    assert (tmp_path / "baseline-run" / "report.md").exists()


def test_unified_runner_mock_patch_resolves_case(tmp_path):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="mock-run",
        results_dir=tmp_path,
        mode="mock-patch",
        mock_patch_dir=Path("eval/mock_patches/sanity-v1/resolved"),
    )
    report = runner.run()

    case_dir = tmp_path / "mock-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    changed = json.loads((case_dir / "changed-files.json").read_text(encoding="utf-8"))

    assert report["resolved"] == 1
    assert verdict["verdict"] == "resolved"
    assert changed == [
        {
            "path": "autopatch_demo/calculator.py",
            "is_test": False,
            "change_type": "modified",
        }
    ]
    assert (case_dir / "patch.diff").read_text(encoding="utf-8").strip()
    assert (case_dir / "test-after.log").exists()
```

- [ ] **Step 2: Run runner tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_runner.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'eval.unified_runner'`.

- [ ] **Step 3: Implement unified runner**

Create `eval/unified_runner.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from eval.config import EvalConfig
from eval.unified_models import (
    PreparedWorkspace,
    UnifiedCase,
    Verdict,
    classify_changed_file,
)
from eval.unified_preparers import LocalFixturePreparer, SWEBenchPreparer


EvalMode = Literal["baseline-only", "mock-patch", "agent"]


class UnifiedEvalRunner:
    def __init__(
        self,
        cases: list[UnifiedCase],
        run_id: str,
        results_dir: Path,
        mode: EvalMode,
        mock_patch_dir: Path | None = None,
        eval_config: EvalConfig | None = None,
    ):
        self.cases = cases
        self.run_id = run_id
        self.results_dir = results_dir
        self.run_dir = results_dir / run_id
        self.mode = mode
        self.mock_patch_dir = mock_patch_dir
        self.eval_config = eval_config or EvalConfig(results_dir=str(results_dir), run_id=run_id)

    def run(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        for case in self.cases:
            results.append(self._run_case(case))
        report = self._build_report(results)
        self._write_json(self.run_dir / "config.json", self._build_config())
        self._write_json(self.run_dir / "report.json", report)
        self._write_report_md(self.run_dir / "report.md", report)
        return report

    def _run_case(self, case: UnifiedCase) -> dict[str, Any]:
        case_dir = self.run_dir / "cases" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        trace_path = case_dir / "trace.jsonl"
        self._append_trace(trace_path, {"type": "case_started", "case_id": case.case_id})
        prepared: PreparedWorkspace | None = None
        try:
            prepared = self._prepare(case)
            self._write_case_artifacts(case_dir, case, prepared)
            baseline = self._run_baseline(case, prepared.workspace, case_dir)
            if baseline != Verdict.BASELINE_READY:
                self._append_trace(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": baseline.value})
                return {"case_id": case.case_id, "verdict": baseline.value, "base_commit": prepared.base_commit}
            if self.mode == "baseline-only":
                self._append_trace(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": Verdict.BASELINE_READY.value})
                return {"case_id": case.case_id, "verdict": Verdict.BASELINE_READY.value, "base_commit": prepared.base_commit}
            if self.mode == "mock-patch":
                self._apply_mock_patch(case, prepared.workspace)
            elif self.mode == "agent":
                self._run_agent(case, prepared.workspace, trace_path)
            verdict = self._validate_patch(case, prepared, case_dir)
            self._append_trace(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": verdict.value})
            return {"case_id": case.case_id, "verdict": verdict.value, "base_commit": prepared.base_commit}
        except Exception as exc:
            self._write_json(
                case_dir / "verdict.json",
                {
                    "case_id": case.case_id,
                    "verdict": Verdict.INFRA_ERROR.value,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "patch_applies": False,
                    "modified_test_files": False,
                    "fail_to_pass": {"total": 0, "passed": 0, "failed": []},
                    "pass_to_pass": {"total": 0, "passed": 0, "failed": []},
                    "timing": {"agent_seconds": None, "verification_seconds": None},
                },
            )
            self._append_trace(trace_path, {"type": "case_finished", "case_id": case.case_id, "verdict": Verdict.INFRA_ERROR.value})
            return {"case_id": case.case_id, "verdict": Verdict.INFRA_ERROR.value, "base_commit": case.base_commit}
        finally:
            if prepared and prepared.cleanup:
                prepared.cleanup()

    def _prepare(self, case: UnifiedCase) -> PreparedWorkspace:
        if case.workspace_strategy == "local_fixture":
            return LocalFixturePreparer(self.run_dir).prepare(case)
        return SWEBenchPreparer(self.eval_config).prepare(case)

    def _run_baseline(self, case: UnifiedCase, workspace: Path, case_dir: Path) -> Verdict:
        f2p = self._run_selectors(workspace, case.fail_to_pass)
        p2p = self._run_selectors(workspace, case.pass_to_pass)
        self._write_test_log(case_dir / "test-before.log", "Baseline Validation", f2p, p2p)
        f2p_passed = [test_id for test_id, data in f2p.items() if data["passed"]]
        p2p_failed = [test_id for test_id, data in p2p.items() if not data["passed"]]
        if f2p_passed:
            verdict = Verdict.INVALID_CASE
            reason = "FAIL_TO_PASS tests already pass before any patch; case metadata or baseline is invalid."
        elif p2p_failed:
            verdict = Verdict.INFRA_ERROR
            reason = "PASS_TO_PASS tests fail before any patch; baseline environment is not valid."
        else:
            verdict = Verdict.BASELINE_READY
            reason = "Baseline is valid: FAIL_TO_PASS failed and PASS_TO_PASS passed before patch."
        self._write_verdict(case_dir, case.case_id, verdict, reason, None, False, None, f2p, p2p)
        return verdict

    def _apply_mock_patch(self, case: UnifiedCase, workspace: Path) -> None:
        if self.mock_patch_dir is None:
            raise ValueError("mock_patch_dir is required for mock-patch mode")
        patch_file = self.mock_patch_dir / f"{case.case_id}.diff"
        result = subprocess.run(["git", "apply", str(patch_file)], cwd=workspace, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Patch did not apply cleanly: {result.stderr.strip()}")

    def _run_agent(self, case: UnifiedCase, workspace: Path, trace_path: Path) -> None:
        from autopatch import run_agent_on_issue

        self._append_trace(trace_path, {"type": "agent_started", "case_id": case.case_id})
        agent_result = run_agent_on_issue(
            issue_text=case.issue_markdown(),
            working_dir=str(workspace),
            repo_language=case.language,
        )
        self._append_trace(trace_path, {"type": "agent_finished", "case_id": case.case_id, "agent_result": agent_result})

    def _validate_patch(self, case: UnifiedCase, prepared: PreparedWorkspace, case_dir: Path) -> Verdict:
        patch_diff = self._git_output(prepared.workspace, ["git", "diff", "HEAD"])
        if prepared.test_patch_files:
            from core.diff_generator import filter_diff

            patch_diff = filter_diff(patch_diff, prepared.test_patch_files)
        (case_dir / "patch.diff").write_text(patch_diff + ("\n" if patch_diff else ""), encoding="utf-8")
        changed_files = self._get_changed_files(prepared.workspace, prepared.test_patch_files)
        self._write_json(case_dir / "changed-files.json", [asdict(item) for item in changed_files])
        modified_test_files = any(item.is_test for item in changed_files)
        if not patch_diff.strip():
            self._write_verdict(case_dir, case.case_id, Verdict.FAILED, "No patch was produced.", False, False, "wrong_fix", {}, {})
            return Verdict.FAILED
        if modified_test_files and not case.allow_test_modifications:
            self._write_verdict(case_dir, case.case_id, Verdict.FAILED, "Patch modified test files, which is prohibited for this benchmark.", True, True, "test_modification", {}, {})
            return Verdict.FAILED
        f2p = self._run_selectors(prepared.workspace, case.fail_to_pass)
        p2p = self._run_selectors(prepared.workspace, case.pass_to_pass)
        self._write_test_log(case_dir / "test-after.log", "Patch Validation", f2p, p2p)
        f2p_failed = [test_id for test_id, data in f2p.items() if not data["passed"]]
        p2p_failed = [test_id for test_id, data in p2p.items() if not data["passed"]]
        if f2p_failed:
            verdict = Verdict.FAILED
            reason = "At least one FAIL_TO_PASS test still fails after patch."
            category = "incomplete_fix"
        elif p2p_failed:
            verdict = Verdict.PARTIAL
            reason = "FAIL_TO_PASS passed, but at least one PASS_TO_PASS test failed after patch."
            category = "regression"
        else:
            verdict = Verdict.RESOLVED
            reason = "FAIL_TO_PASS and PASS_TO_PASS passed after patch."
            category = None
        self._write_verdict(case_dir, case.case_id, verdict, reason, True, False, category, f2p, p2p)
        return verdict

    def _get_changed_files(self, workspace: Path, excluded: set[str]) -> list[Any]:
        output = self._git_output(workspace, ["git", "diff", "--name-status", "HEAD"])
        files = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            path = parts[-1]
            if path in excluded:
                continue
            files.append(classify_changed_file(status, path))
        return files

    def _write_case_artifacts(self, case_dir: Path, case: UnifiedCase, prepared: PreparedWorkspace) -> None:
        self._write_json(case_dir / "case.json", case.to_case_json())
        (case_dir / "issue.md").write_text(case.issue_markdown(), encoding="utf-8")
        self._write_json(
            case_dir / "workspace-info.json",
            {
                "workspace": str(prepared.workspace),
                "base_commit": prepared.base_commit,
                "workspace_strategy": case.workspace_strategy,
                "test_patch_files": sorted(prepared.test_patch_files),
                "docker_container": prepared.docker_container,
                "docker_container_path": prepared.docker_container_path,
            },
        )

    def _run_selectors(self, workspace: Path, selectors: list[str]) -> dict[str, dict[str, Any]]:
        results = {}
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

    def _build_config(self) -> dict[str, Any]:
        return {
            "protocol_version": "2026-06-14",
            "run_id": self.run_id,
            "dataset_name": self.cases[0].dataset_name if self.cases else None,
            "case_ids": [case.case_id for case in self.cases],
            "agent_config": {"mode": self.mode},
            "environment": {"python_version": sys.version.split()[0], "docker_enabled": self.eval_config.use_docker},
        }

    def _build_report(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {}
        for result in results:
            counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
        return {
            "run_id": self.run_id,
            "dataset_name": self.cases[0].dataset_name if self.cases else None,
            "total_cases": len(results),
            "baseline_ready": counts.get(Verdict.BASELINE_READY.value, 0),
            "resolved": counts.get(Verdict.RESOLVED.value, 0),
            "partial": counts.get(Verdict.PARTIAL.value, 0),
            "failed": counts.get(Verdict.FAILED.value, 0),
            "agent_timeout": counts.get(Verdict.AGENT_TIMEOUT.value, 0),
            "invalid_case": counts.get(Verdict.INVALID_CASE.value, 0),
            "infra_error": counts.get(Verdict.INFRA_ERROR.value, 0),
            "cases": results,
        }

    def _write_verdict(
        self,
        case_dir: Path,
        case_id: str,
        verdict: Verdict,
        reason: str,
        patch_applies: bool | None,
        modified_test_files: bool,
        failure_category: str | None,
        fail_to_pass: dict[str, dict[str, Any]],
        pass_to_pass: dict[str, dict[str, Any]],
    ) -> None:
        f2p_passed = [test_id for test_id, data in fail_to_pass.items() if data["passed"]]
        f2p_failed = [test_id for test_id, data in fail_to_pass.items() if not data["passed"]]
        p2p_passed = [test_id for test_id, data in pass_to_pass.items() if data["passed"]]
        p2p_failed = [test_id for test_id, data in pass_to_pass.items() if not data["passed"]]
        data: dict[str, Any] = {
            "case_id": case_id,
            "verdict": verdict.value,
            "reason": reason,
            "patch_applies": patch_applies,
            "modified_test_files": modified_test_files,
            "fail_to_pass": {"total": len(fail_to_pass), "passed": len(f2p_passed), "failed": f2p_failed},
            "pass_to_pass": {"total": len(pass_to_pass), "passed": len(p2p_passed), "failed": p2p_failed},
            "timing": {"agent_seconds": None, "verification_seconds": None},
        }
        if failure_category is not None:
            data["failure_category"] = failure_category
        self._write_json(case_dir / "verdict.json", data)

    def _write_test_log(self, path: Path, title: str, fail_to_pass: dict[str, dict[str, Any]], pass_to_pass: dict[str, dict[str, Any]]) -> None:
        lines = [f"# {title}", ""]
        for group_name, results in (("FAIL_TO_PASS", fail_to_pass), ("PASS_TO_PASS", pass_to_pass)):
            lines.append(f"## {group_name}")
            lines.append("")
            for selector, data in results.items():
                status = "PASSED" if data["passed"] else "FAILED"
                lines.append(f"### {selector}")
                lines.append(f"Status: {status} (exit {data['returncode']})")
                if data["stdout"].strip():
                    lines += ["", "stdout:", "```", data["stdout"].rstrip(), "```"]
                if data["stderr"].strip():
                    lines += ["", "stderr:", "```", data["stderr"].rstrip(), "```"]
                lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_report_md(self, path: Path, report: dict[str, Any]) -> None:
        lines = [
            f"# {report['dataset_name']} Report",
            "",
            f"Run ID: `{report['run_id']}`",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Total cases | {report['total_cases']} |",
            f"| Baseline ready | {report['baseline_ready']} |",
            f"| Resolved | {report['resolved']} |",
            f"| Partial | {report['partial']} |",
            f"| Failed | {report['failed']} |",
            f"| Agent timeout | {report['agent_timeout']} |",
            f"| Invalid case | {report['invalid_case']} |",
            f"| Infra error | {report['infra_error']} |",
            "",
            "## Cases",
            "",
            "| Case | Verdict | Base commit |",
            "|---|---|---|",
        ]
        for case in report["cases"]:
            lines.append(f"| `{case['case_id']}` | `{case['verdict']}` | `{case.get('base_commit') or ''}` |")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _append_trace(self, path: Path, event: dict[str, Any]) -> None:
        payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _git_output(self, cwd: Path, cmd: list[str]) -> str:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_models.py tests/test_unified_providers.py tests/test_unified_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit task 4**

```bash
git add eval/unified_runner.py tests/test_unified_runner.py
git commit -m "feat: add unified evaluation runner"
```

---

### Task 5: Unified CLI

**Files:**
- Create: `eval/unified.py`
- Test: create `tests/test_unified_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_unified_cli.py`:

```python
from eval.unified import build_parser, resolve_cases


def test_parser_accepts_sanity_agent_mode():
    args = build_parser().parse_args(["--dataset", "sanity-v2", "--mode", "agent"])

    assert args.dataset == "sanity-v2"
    assert args.mode == "agent"


def test_resolve_cases_loads_selected_sanity_case():
    args = build_parser().parse_args(
        [
            "--dataset",
            "sanity-v1",
            "--mode",
            "baseline-only",
            "--case-ids",
            "py-single-file",
        ]
    )

    cases = resolve_cases(args)

    assert [case.case_id for case in cases] == ["py-single-file"]
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_cli.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'eval.unified'`.

- [ ] **Step 3: Implement CLI**

Create `eval/unified.py`:

```python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from eval.config import EvalConfig
from eval.unified_providers import LocalSanityProvider, SWEBenchProvider, SWEBenchSmokeProvider
from eval.unified_runner import UnifiedEvalRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run unified AutoPatch evaluations.")
    parser.add_argument("--dataset", required=True, help="sanity-v1, sanity-v2, swebench-smoke, swebench-lite, or local JSON path")
    parser.add_argument("--mode", required=True, choices=["baseline-only", "mock-patch", "agent"])
    parser.add_argument("--results-dir", default="eval/results")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cases-dir", default=None)
    parser.add_argument("--mock-patch-dir", default=None)
    parser.add_argument("--dataset-split", default="test")
    parser.add_argument("--instance-ids", nargs="+", default=None)
    parser.add_argument("--case-ids", nargs="+", default=None)
    parser.add_argument("--repos", nargs="+", default=None)
    parser.add_argument("--max-instances", type=int, default=None)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--workdir", default="/tmp/autopatch_eval")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--keep-image", action="store_true")
    return parser


def resolve_cases(args: argparse.Namespace):
    if args.dataset in {"sanity-v1", "sanity-v2"}:
        cases_dir = Path(args.cases_dir) if args.cases_dir else Path("eval/cases") / args.dataset
        cases = LocalSanityProvider(dataset_name=args.dataset, cases_dir=cases_dir).load()
        selected = set(args.case_ids or args.instance_ids or [])
        return [case for case in cases if not selected or case.case_id in selected]
    if args.dataset == "swebench-smoke":
        return SWEBenchSmokeProvider(dataset_split=args.dataset_split).load()
    dataset_name = "princeton-nlp/SWE-bench_Lite" if args.dataset == "swebench-lite" else args.dataset
    return SWEBenchProvider(
        dataset_name=dataset_name,
        dataset_split=args.dataset_split,
        instance_ids=args.instance_ids or args.case_ids,
        repos=args.repos,
        max_instances=args.max_instances,
        shuffle=args.shuffle,
        seed=args.seed,
    ).load()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.mode == "mock-patch" and not args.mock_patch_dir:
        parser.error("--mock-patch-dir is required when --mode mock-patch")
    cases = resolve_cases(args)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_unified_eval")
    eval_config = EvalConfig(
        workdir_base=args.workdir,
        install_deps=not args.no_install,
        results_dir=args.results_dir,
        run_id=run_id,
        use_docker=args.docker,
        keep_image=args.keep_image,
    )
    runner = UnifiedEvalRunner(
        cases=cases,
        run_id=run_id,
        results_dir=Path(args.results_dir),
        mode=args.mode,
        mock_patch_dir=Path(args.mock_patch_dir) if args.mock_patch_dir else None,
        eval_config=eval_config,
    )
    runner.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI and focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_cli.py tests/test_unified_models.py tests/test_unified_providers.py tests/test_unified_runner.py -q
.venv/bin/python -m eval.unified --dataset sanity-v1 --mode baseline-only --case-ids py-single-file --results-dir /tmp/autopatch-unified-smoke --run-id sanity-one
```

Expected: pytest PASS, CLI exits 0 and writes `/tmp/autopatch-unified-smoke/sanity-one/report.json`.

- [ ] **Step 5: Commit task 5**

```bash
git add eval/unified.py tests/test_unified_cli.py
git commit -m "feat: add unified evaluation cli"
```

---

### Task 6: Documentation And Compatibility Notes

**Files:**
- Modify: `docs/evaluation-protocol.md`
- Modify: `README.md`

- [ ] **Step 1: Update evaluation protocol docs**

Add this section near the top of `docs/evaluation-protocol.md` after the status note:

```markdown
## 推荐入口

新的统一评测入口是：

```bash
python -m eval.unified --dataset sanity-v1 --mode baseline-only
python -m eval.unified --dataset sanity-v2 --mode agent
python -m eval.unified --dataset swebench-smoke --mode agent
python -m eval.unified --dataset swebench-lite --mode agent --instance-ids <instance_id>
```

`python -m eval.sanity` 和 `python run_eval.py` 仍保留为兼容入口；新评测结果应优先使用 `eval.unified` 产物目录和 verdict 定义。
```

- [ ] **Step 2: Update README**

Add this section after the existing CLI options section in `README.md`:

```markdown
## Evaluation

AutoPatch uses one evaluation protocol for local sanity benchmarks and SWE-bench style cases.

```bash
# Validate local fixtures without model calls
python -m eval.unified --dataset sanity-v1 --mode baseline-only

# Run the real agent on richer local sanity cases
python -m eval.unified --dataset sanity-v2 --mode agent

# Run a pinned smoke set of real SWE-bench Lite instances
python -m eval.unified --dataset swebench-smoke --mode agent

# Run selected SWE-bench Lite instances
python -m eval.unified --dataset swebench-lite --mode agent --instance-ids <instance_id>
```

Results are written to `eval/results/<run_id>/` with per-case `case.json`, `issue.md`, `patch.diff`, `changed-files.json`, test logs, and `verdict.json`.
```

- [ ] **Step 3: Run docs-adjacent smoke checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_cli.py tests/test_unified_runner.py -q
rg -n "eval.unified|swebench-smoke" README.md docs/evaluation-protocol.md
```

Expected: pytest PASS, `rg` finds the new commands in both docs.

- [ ] **Step 4: Commit task 6**

```bash
git add README.md docs/evaluation-protocol.md
git commit -m "docs: document unified evaluation cli"
```

---

### Task 7: Final Verification

**Files:**
- No expected source changes unless verification exposes a defect.

- [ ] **Step 1: Run default relevant test suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_unified_models.py tests/test_unified_providers.py tests/test_unified_runner.py tests/test_unified_cli.py tests/test_sanity_runner.py tests/test_docker_verify.py tests/test_docker_env.py -q
```

Expected: PASS.

- [ ] **Step 2: Run unified sanity baseline smoke**

Run:

```bash
.venv/bin/python -m eval.unified --dataset sanity-v1 --mode baseline-only --results-dir /tmp/autopatch-unified-final --run-id sanity-v1-baseline
```

Expected: exits 0 and writes `/tmp/autopatch-unified-final/sanity-v1-baseline/report.json` with `total_cases: 5`, `baseline_ready: 4`, and `invalid_case: 1`.

- [ ] **Step 3: Run unified sanity mock patch smoke**

Run:

```bash
.venv/bin/python -m eval.unified --dataset sanity-v1 --mode mock-patch --mock-patch-dir eval/mock_patches/sanity-v1/resolved --results-dir /tmp/autopatch-unified-final --run-id sanity-v1-mock
```

Expected: exits 0 and writes `/tmp/autopatch-unified-final/sanity-v1-mock/report.json` with `resolved: 4` and `invalid_case: 1`.

- [ ] **Step 4: Inspect git state**

Run:

```bash
git status --short
```

Expected: no unexpected uncommitted changes except pre-existing user edits, currently `docs/evaluation-runs.md`.

- [ ] **Step 5: Report outcome**

Summarize:

- New files added.
- Commands run.
- Any skipped network or Docker SWE-bench integration checks.
- Reminder that existing `docs/evaluation-runs.md` had pre-existing uncommitted edits if still present.
