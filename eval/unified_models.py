from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set


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
    base_commit: Optional[str]
    issue_title: str
    issue_body: str
    language: str
    fail_to_pass: List[str]
    pass_to_pass: List[str]
    expected_files: List[str] = field(default_factory=list)
    allow_test_modifications: bool = False
    workspace_strategy: WorkspaceStrategy = "local_fixture"
    fixture_path: Optional[Path] = None
    swebench_instance_id: Optional[str] = None
    swebench_test_patch: str = ""
    swebench_gold_patch: str = ""
    environment_setup_commit: Optional[str] = None
    version: Optional[str] = None
    analysis_notes: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def issue_markdown(self) -> str:
        return f"# {self.issue_title}\n\n{self.issue_body}\n"

    def to_case_json(self) -> Dict[str, Any]:
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
            "swebench_test_patch": self.swebench_test_patch,
            "swebench_gold_patch": self.swebench_gold_patch,
            "analysis_notes": self.analysis_notes,
            "raw": self.raw,
            "environment_setup_commit": self.environment_setup_commit,
            "version": self.version,
        }


@dataclass(frozen=True)
class PreparedWorkspace:
    workspace: Path
    base_commit: str
    test_patch_files: Set[str] = field(default_factory=set)
    cleanup: Optional[Any] = None
    docker_container: Optional[str] = None
    docker_container_path: Optional[str] = None


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
