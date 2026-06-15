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

    @staticmethod
    def _normalize_expected_files(case: dict) -> List[str]:
        expected_files = case.get("expected_files")
        if expected_files is None:
            expected_files = case.get("expected_modified_files")
        if expected_files is None:
            return []
        if isinstance(expected_files, str):
            return [expected_files]
        return expected_files

    def load(self) -> List[UnifiedCase]:
        cases = []
        for case_file in sorted(self.cases_dir.glob("*.json")):
            case = json.loads(case_file.read_text(encoding="utf-8"))

            expected_files = self._normalize_expected_files(case)

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

    def _resolved_dataset_name(self) -> str:
        dataset_path = Path(self.dataset_name)
        if self.dataset_name == "princeton-nlp/SWE-bench_Lite":
            return "swebench-lite"
        if dataset_path.exists() and dataset_path.suffix == ".json":
            return dataset_path.stem
        return self.dataset_name

    def load(self) -> List[UnifiedCase]:
        items = [_parse_item(item) for item in _load_raw(self.dataset_name, self.dataset_split)]
        filtered_items = items

        if self.instance_ids is not None:
            items_by_id = {item.instance_id: item for item in items}
            filtered_items = [
                items_by_id[instance_id]
                for instance_id in self.instance_ids
                if instance_id in items_by_id
            ]
        if self.repos is not None:
            repo_set = set(self.repos)
            filtered_items = [item for item in filtered_items if item.repo in repo_set]

        if self.shuffle:
            random.seed(self.seed)
            random.shuffle(filtered_items)

        if self.max_instances is not None:
            filtered_items = filtered_items[: self.max_instances]

        return [
            UnifiedCase(
                case_id=item.instance_id,
                dataset_name=self._resolved_dataset_name(),
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
            for item in filtered_items
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
