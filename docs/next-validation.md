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
| Real model smoke | Anthropic returned HTTP 401 invalid x-api-key; recorded as infra_error/model_service_error |

Machine-readable aggregate reports are in [evidence/next](evidence/next).
Full raw artifacts remain in the ignored `eval/results/` directory.

The wrong-plan scenario resolves only with replanning in this controlled test.
The classifier and coder are scripted in these two runs; the actual graph,
fixture subprocess tests and independent patch validation run normally.
These numbers **are not LLM effectiveness scores**. The v1/v2 checks above
also do not substitute for real model regression runs.

## Open verification

- The configured API Key is rejected by `https://api.anthropic.com` with HTTP
  401 `invalid x-api-key`; `.env` has no alternate `OPENAI_BASE_URL`. Actual
  model-driven repair, sanity-v1/v2/v3 comparisons and SWE-bench smoke cannot
  be claimed successful. The attempted live run is preserved in
  `eval/results/next-agent-auth-classified/`; its aggregate report is included
  in `docs/evidence/next/`.
- Docker Hub direct pulls timed out. The identical public Python base was pulled
  through [Google's official public cache](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images).
  No daemon-wide registry or network configuration was changed.
- PostgreSQL tests use controlled model responses, verifying real persistence
  and graph resume rather than model reasoning.
- SWE-bench prepared image/interpreter/workspace now propagate into the sandbox;
  this handoff has regression tests but the large official instances remain
  unexecuted while model authentication is unavailable.
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
