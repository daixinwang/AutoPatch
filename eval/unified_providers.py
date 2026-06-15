import json
import random
from pathlib import Path
from typing import List, Optional

from eval.dataset import _load_raw, _parse_item
from eval.unified_models import UnifiedCase


DEFAULT_SWEBENCH_SMOKE_IDS = [
    "pallets__flask-4045",
    "psf__requests-1963",
    "sympy__sympy-11400",
]


class LocalSanityProvider:
    def __init__(self, dataset_name: str, cases_dir: Path):
        self.dataset_name = dataset_name
        self.cases_dir = cases_dir

    def load(self) -> List[UnifiedCase]:
        cases = []
        for case_file in sorted(self.cases_dir.glob("*.json")):
            case = json.loads(case_file.read_text(encoding="utf-8"))

            expected_files = case.get("expected_files")
            if expected_files is None:
                expected_files = case.get("expected_modified_files", [])
            elif isinstance(expected_files, str):
                expected_files = [expected_files]

            source = case.get("source", "local_sanity")
            cases.append(
                UnifiedCase(
                    case_id=case["case_id"],
                    dataset_name=self.dataset_name,
                    source=source,
                    repo=case.get("repo", f"local/{case['case_id']}"),
                    base_commit=case.get("base_commit"),
                    issue_title=case["issue_title"],
                    issue_body=case["issue_body"],
                    language=case["language"],
                    fail_to_pass=case.get("fail_to_pass", []),
                    pass_to_pass=case.get("pass_to_pass", []),
                    expected_files=expected_files,
                    allow_test_modifications=case.get("allow_test_modifications", False),
                    fixture_path=Path(case["fixture_path"]),
                    raw=case,
                )
            )

        return cases


class SWEBenchProvider:
    def __init__(
        self,
        dataset_name: str,
        dataset_split: str,
        instance_ids: Optional[List[str]] = None,
        repos: Optional[List[str]] = None,
        shuffle: bool = False,
        seed: int = 42,
        max_instances: Optional[int] = None,
    ):
        self.dataset_name = dataset_name
        self.dataset_split = dataset_split
        self.instance_ids = instance_ids
        self.repos = repos
        self.shuffle = shuffle
        self.seed = seed
        self.max_instances = max_instances

    def load(self) -> List[UnifiedCase]:
        items = [_parse_item(item) for item in _load_raw(self.dataset_name, self.dataset_split)]

        if self.instance_ids is not None:
            instance_id_set = set(self.instance_ids)
            items = [item for item in items if item.instance_id in instance_id_set]

        if self.repos is not None:
            repo_set = set(self.repos)
            items = [item for item in items if item.repo in repo_set]

        if self.shuffle:
            random.seed(self.seed)
            random.shuffle(items)

        if self.max_instances is not None:
            items = items[: self.max_instances]

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
                swebench_instance_id=item.instance_id,
                workspace_strategy="swebench_instance",
                swebench_test_patch=item.test_patch,
                swebench_gold_patch=item.patch,
                environment_setup_commit=item.environment_setup_commit,
                version=item.version,
                raw=item.__dict__,
            )
            for item in items
        ]


class SWEBenchSmokeProvider(SWEBenchProvider):
    def __init__(
        self,
        dataset_name: str,
        dataset_split: str,
        repos: Optional[List[str]] = None,
        shuffle: bool = False,
        seed: int = 42,
        max_instances: Optional[int] = None,
    ):
        super().__init__(
            dataset_name=dataset_name,
            dataset_split=dataset_split,
            instance_ids=DEFAULT_SWEBENCH_SMOKE_IDS,
            repos=repos,
            shuffle=shuffle,
            seed=seed,
            max_instances=max_instances,
        )
