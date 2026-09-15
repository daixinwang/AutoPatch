# AutoPatch Next implementation contract

The implementation and operational boundaries are documented in
[architecture-next.md](docs/architecture-next.md). The supplied design targets
five P0 areas: typed state, deterministic test execution, bounded failure recovery,
container isolation, and reproducible recovery evaluation.

## Acceptance checklist

- [x] Validated plans, profiles, test plans/reports, review decisions and diagnoses.
- [x] Manifest-driven command registry with path validation.
- [x] Failure classifier, evidence-aware replanner and independent recovery limits.
- [x] Docker backend with resource/network/credential boundaries and cleanup.
- [x] Default isolated clone for local CLI workspaces.
- [x] Machine verification receipt required before PR creation.
- [x] Five controlled failure cases and full/no_replanner scripted experiments.
- [x] Offline tests for graph recovery and checkpointed counters.
- [x] Live Docker isolation, timeout, cleanup and Python pytest integration.
- [x] Live PostgreSQL checkpoint/resume integration with controlled model responses.
- [ ] Real model sanity-v1/v2/v3 and full/no_replanner experiments.
- [ ] Fixed SWE-bench smoke instances with real model and container environment.

Pending checks are environment-dependent and must not be described as passed.
No automatic merge, arbitrary shell agent, framework migration or frontend
redesign is included.
