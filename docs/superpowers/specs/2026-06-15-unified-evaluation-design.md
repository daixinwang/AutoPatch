# Unified Evaluation Design

Date: 2026-06-15

## Goal

Unify AutoPatch evaluation into one protocol and runner while preserving the existing `sanity-v1` and `sanity-v2` benchmarks. The unified evaluation should also support real SWE-bench usage in two forms:

- `swebench-smoke`: a small pinned set of actual SWE-bench Lite instances for stable smoke testing.
- `swebench-lite`: dynamic loading from HuggingFace or local JSON with filters such as `--instance-ids`, `--repos`, and `--max-instances`.

The design should reduce duplicated evaluation logic without breaking the existing sanity workflow.

## Non-Goals

- Do not rewrite AutoPatch agent behavior or prompts.
- Do not remove existing `eval.sanity` or `run_eval.py` immediately.
- Do not require Docker for local sanity cases.
- Do not claim full SWE-bench parity in the first unified runner pass; the first pass should integrate the existing SWE-bench path under the same reporting protocol.

## CLI Shape

Add a unified entry point:

```bash
python -m eval.unified --dataset sanity-v1 --mode baseline-only
python -m eval.unified --dataset sanity-v2 --mode agent
python -m eval.unified --dataset swebench-smoke --mode agent
python -m eval.unified --dataset swebench-lite --mode agent --instance-ids django__django-xxxxx
```

Supported modes:

- `baseline-only`: prepare each case and validate pre-patch tests only.
- `mock-patch`: apply fixed patch files and classify the result.
- `agent`: run the real AutoPatch agent and classify the result.

## Architecture

Introduce three explicit boundaries.

### Dataset Providers

Providers convert dataset-specific metadata into a common case model.

- `LocalSanityProvider`
  - Reads `eval/cases/sanity-v1/*.json` or `eval/cases/sanity-v2/*.json`.
  - Keeps existing fixture paths and test selectors unchanged.
  - Produces cases whose workspace strategy is `local_fixture`.

- `SWEBenchSmokeProvider`
  - Uses a pinned list of real SWE-bench Lite instance ids.
  - Loads those instances through the SWE-bench provider.
  - Produces cases whose workspace strategy is `swebench_instance`.

- `SWEBenchProvider`
  - Loads `princeton-nlp/SWE-bench_Lite` or a local JSON file.
  - Supports `--instance-ids`, `--repos`, `--max-instances`, `--shuffle`, and `--seed`.
  - Preserves gold patch metadata for analysis only; it must not be passed to the agent.

### Workspace Preparers

Preparers are responsible for making a workspace at the expected broken baseline.

- `LocalFixturePreparer`
  - Copies the fixture directory.
  - Runs `git init`, `git add .`, and `git commit -m baseline`.
  - Returns the generated base commit.

- `SWEBenchPreparer`
  - Reuses the existing `InstanceEnvironment` and optional `DockerEnvironment` logic.
  - Checks out the SWE-bench `base_commit`.
  - Applies `test_patch` so FAIL_TO_PASS tests exist.
  - Records files introduced or modified by `test_patch` so agent diff filtering still works.

### Case Runner

The unified runner should operate on prepared cases, not dataset internals.

For every case:

1. Write `case.json`, `issue.md`, `workspace-info.json`, and initial `trace.jsonl`.
2. Run baseline validation:
   - all `FAIL_TO_PASS` selectors should fail before the agent patch.
   - all `PASS_TO_PASS` selectors should pass before the agent patch.
3. If baseline is invalid, classify as `invalid_case` or `infra_error` and skip the agent.
4. For `mock-patch`, apply `<case_id>.diff`.
5. For `agent`, call `autopatch.run_agent_on_issue(issue_text, workspace, language)`.
6. Save the resulting `patch.diff`.
7. Save `changed-files.json`.
8. Reject prohibited test-file modifications.
9. Run post-patch `FAIL_TO_PASS` and `PASS_TO_PASS`.
10. Write `test-after.log`, `verdict.json`, `report.json`, and `report.md`.

## Common Case Model

Use a normalized model with fields equivalent to:

```text
case_id
dataset_name
source
repo
base_commit
issue_title
issue_body
language
fail_to_pass
pass_to_pass
expected_files
allow_test_modifications
workspace_strategy
fixture_path
swebench_instance_id
swebench_test_patch
swebench_gold_patch
```

`expected_files`, `swebench_gold_patch`, and evaluator notes are analysis-only fields. They must not be included in `issue.md`.

## Verdict Rules

Use the protocol verdicts for both sanity and SWE-bench cases:

- `resolved`: non-empty patch, clean classification, no prohibited test modifications, all F2P and P2P selectors pass.
- `partial`: all F2P selectors pass, at least one P2P selector fails.
- `failed`: agent ran but did not solve the case, produced no patch, modified tests, or left F2P failing.
- `agent_timeout`: agent exceeded configured timeout.
- `infra_error`: environment or setup issue prevents evaluating agent performance.
- `invalid_case`: case metadata or baseline is invalid, such as F2P passing before any patch.

The first implementation may map existing SWE-bench `error` setup failures to `infra_error` and existing `timeout` to `agent_timeout`.

## Output Layout

All datasets should write the same structure:

```text
eval/results/<run_id>/
  config.json
  report.json
  report.md
  cases/
    <case_id>/
      case.json
      issue.md
      trace.jsonl
      patch.diff
      changed-files.json
      test-before.log
      test-after.log
      verdict.json
      workspace-info.json
```

For SWE-bench, `case_id` should be the SWE-bench `instance_id`.

## Compatibility Plan

Keep existing entry points during migration:

- `python -m eval.sanity ...` remains usable.
- `python run_eval.py ...` remains usable.

After the unified runner exists, the old entry points can become thin wrappers or be documented as legacy. The first implementation should avoid deleting working behavior.

## Testing Plan

Add focused tests for:

- Loading `sanity-v1` and `sanity-v2` through `LocalSanityProvider`.
- Loading and filtering SWE-bench data through `SWEBenchProvider` using a local JSON fixture.
- `swebench-smoke` provider selecting a pinned subset.
- Baseline-only sanity execution.
- Mock-patch sanity execution.
- Unified verdict classification for `resolved`, `partial`, `failed`, `invalid_case`, and `infra_error`.
- Report output shape and required files.

Integration tests that require network or Docker should be opt-in, not part of the default test suite.

## Open Implementation Choices

- The exact pinned `swebench-smoke` instance ids should be chosen during implementation from known small Python cases that are practical to run locally or via existing Docker support.
- If HuggingFace data is unavailable because of network restrictions, the runner should support local JSON input for repeatable tests.
