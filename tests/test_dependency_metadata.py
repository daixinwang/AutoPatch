"""
Dependency metadata consistency checks.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_anthropic_runtime_dependency_is_declared() -> None:
    """The runtime dependency used by agent.graph must be in both dependency manifests."""
    requirement_lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    declared_requirements = {
        line.split("#", 1)[0].strip()
        for line in requirement_lines
        if line.strip() and not line.lstrip().startswith("#")
    }

    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert any(dep.startswith("langchain-anthropic") for dep in declared_requirements)
    assert '"langchain-anthropic' in pyproject_text
