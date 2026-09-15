"""Registry IDs and bounded relative selectors, never model-authored shell."""

from pathlib import Path

from agent.models import ProjectProfile, TestPlan, TestReport

TEST_COMMAND_REGISTRY = {
    "python_pytest": ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"],
    "node_npm_test": ["npm", "test"],
    "go_test_all": ["go", "test", "./..."],
    "cargo_test": ["cargo", "test"],
    "maven_test": ["mvn", "test"],
    "gradle_test": ["gradle", "test"],
    "make_test": ["make", "test"],
}


def resolve_commands(profile: ProjectProfile, plan: TestPlan, workspace: Path):
    root = Path(workspace).resolve()
    if not plan.commands or len(set(plan.commands)) != len(plan.commands):
        raise ValueError("No tests selected or duplicate command IDs")
    targets = []
    for target in plan.targeted_paths:
        path = Path(target.split("::", 1)[0])
        if (
            path.is_absolute()
            or target.startswith("-")
            or "\\" in target
            or not (root / path).resolve().is_relative_to(root)
            or not (root / path).exists()
        ):
            raise ValueError(f"Invalid test selection: {target}")
        targets.append("./" + target)
    resolved = []
    for command in plan.commands:
        if command not in profile.default_test_commands or command not in TEST_COMMAND_REGISTRY:
            raise ValueError(f"Command does not match project profile: {command}")
        argv = list(TEST_COMMAND_REGISTRY[command])
        if targets and command != "python_pytest":
            raise ValueError("Target selectors currently supported only for pytest")
        resolved.append((command, argv + targets))
    return resolved


def execute_plan(profile, plan, workspace, backend):
    results = []
    for command, argv in resolve_commands(profile, plan, workspace):
        result = backend.run(argv, workspace)
        result.command = command
        results.append(result)
    return TestReport(
        project_type=profile.primary_language,
        results=results,
        all_required_passed=bool(results) and all(r.status == "passed" and r.exit_code == 0 for r in results),
    )
