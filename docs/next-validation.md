# Next validation — 2026-09-15

## Executed checks

| Check | Observed result |
|---|---|
| Final full unit/integration suite | 191 passed, no skipped tests; one dependency deprecation warning |
| New-module Ruff checks | Passed |
| Frontend `npm ci` and `npm run build` | Passed; Vite output generated |
| sanity-v1, existing resolved mock patches | 4 resolved, 1 correctly invalid baseline |
| sanity-v2, baseline-only | All 5 baseline_ready |
| sanity-v3 scripted full | 3 resolved, 1 bounded failed, 1 infra_error |
| sanity-v3 scripted no_replanner | 2 resolved, 2 bounded failed, 1 infra_error |
| Git push dry-run to `origin/shuai` | Authorized with the existing GitHub login |
| Docker engine | 29.7.2 reachable |
| Python sandbox image | Built successfully using the Google public Docker Hub cache |
| Live Docker tests | Host-file isolation, no credentials/socket, timeout cleanup, and pytest failure → pass verified |
| Live PostgreSQL checkpoint | Replanner checkpoint persisted and resumed on a separate temporary PostgreSQL container |
| Real model connectivity | Ark `/api/plan` with `ark-code-latest` succeeded; service returned `deepseek-v4-1-flash` |
| Real model repair smoke | Thinking mode rejected forced tool choice; disabling thinking fixed that error, but two repair attempts failed ExecutionPlan validation due to malformed model tool arguments |
| Ark compatibility regression | 10 passed, 1 opt-in PostgreSQL test skipped; one dependency deprecation warning |

Machine-readable aggregate reports are in [evidence/next](evidence/next).
Full raw artifacts remain in the ignored `eval/results/` directory.

The wrong-plan scenario resolves only with replanning in this controlled test.
The classifier and coder are scripted in these two runs; the actual graph,
fixture subprocess tests and independent patch validation run normally.
These numbers **are not LLM effectiveness scores**. The v1/v2 checks above
also do not substitute for real model regression runs.

## Open verification

- The user's current Ark console specifies the Anthropic endpoint
  `https://ark.cn-beijing.volces.com/api/plan` and model `ark-code-latest`.
  Local configuration now uses these for all four roles, with
  `AUTOPATCH_DISABLE_THINKING=true`. The `/api/plan/v3` endpoint is for the
  OpenAI protocol and does not match this project's Anthropic client.
  Connectivity and a simple structured-output probe succeeded. However,
  two real repair attempts returned invalid ExecutionPlan tool arguments;
  inspection found malformed JSON, not a token-limit stop. These responses
  are rejected by validation. Actual model-driven repair, full comparisons
  and SWE-bench smoke remain unverified. Aggregate reports for both attempts
  are included in `docs/evidence/next/`; raw artifacts remain in ignored
  `eval/results/next-ark-plan-compatible/` and `next-ark-plan-confirm/`.
  Earlier authentication failures are retained as historical evidence.
- Docker Hub direct pulls timed out. The identical public Python base was pulled
  through [Google's official public cache](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images).
  No daemon-wide registry or network configuration was changed.
- PostgreSQL tests use controlled model responses, verifying real persistence
  and graph resume rather than model reasoning.
- SWE-bench prepared image/interpreter/workspace now propagate into the sandbox;
  this handoff has regression tests but the large official instances remain
  unexecuted; the current real model repair smoke has not passed.
- `langgraph-checkpoint-postgres==2.0.19` is pinned to retain LangGraph 0.2;
  later 2.x and 3.x releases warn that they require a newer graph runtime.

## Reproduction

Use a virtual environment, install `requirements.txt` plus pytest,
pytest-asyncio and httpx. Offline tests require a nonsecret test placeholder in
`OPENAI_API_KEY` because upstream creates model clients on graph import. No
default unit test calls the model API. Git fixture tests require a local test
author/committer identity. Tokenizer data must be cached or downloadable.

```sh
pytest -q
python -m eval.unified --dataset sanity-v1 --mode mock-patch --mock-patch-dir eval/mock_patches/sanity-v1/resolved
python -m eval.unified --dataset sanity-v2 --mode baseline-only
python -m eval.unified --dataset sanity-v3 --mode scripted --ablation full
python -m eval.unified --dataset sanity-v3 --mode scripted --ablation no_replanner
docker build -f sandbox.Dockerfile -t autopatch-sandbox:latest .
# Optional public mirror when Docker Hub is unavailable:
docker build --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim -f sandbox.Dockerfile -t autopatch-sandbox:latest .
# Opt-in environment variables for pytest:
# AUTOPATCH_RUN_DOCKER_TESTS=1
# AUTOPATCH_TEST_POSTGRES_DSN=postgresql://.../isolated_test_database
```

Frontend installation reported 11 dependency audit findings in the existing
lockfile. No automatic major-version dependency changes were made in this
backend-focused branch. The upstream repository also has pre-existing global
Ruff findings; new modules are checked separately.
