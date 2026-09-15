"""Read manifests without importing or running repository code."""

import json
from pathlib import Path

from agent.models import ProjectProfile


def profile_project(workspace: Path) -> ProjectProfile:
    root = Path(workspace).resolve()
    groups = [
        (
            "Python",
            ("pyproject.toml", "setup.py", "requirements.txt", "pytest.ini", "setup.cfg"),
            "pytest",
            "python_pytest",
        ),
        ("Node", ("package.json",), "npm", "node_npm_test"),
        ("Go", ("go.mod",), "go", "go_test_all"),
        ("Rust", ("Cargo.toml",), "cargo", "cargo_test"),
        ("Java", ("pom.xml",), "maven", "maven_test"),
        ("Java", ("build.gradle", "build.gradle.kts", "gradlew"), "gradle", "gradle_test"),
        ("Generic", ("Makefile",), "make", "make_test"),
    ]
    manifests, frameworks, commands, languages = [], [], [], []
    for language, names, framework, command in groups:
        found = [name for name in names if (root / name).is_file() and (root / name).resolve().is_relative_to(root)]
        if not found:
            continue
        manifests.extend(found)
        languages.append(language)
        if language == "Node":
            try:
                data = json.loads((root / "package.json").read_text(encoding="utf-8"))
                if not isinstance(data.get("scripts", {}).get("test"), str):
                    continue
            except (OSError, ValueError, AttributeError):
                continue
        frameworks.append(framework)
        commands.append(command)
    # Many small Python fixtures intentionally have no packaging metadata.
    if (
        not languages
        and any(root.glob("test*.py"))
        or not languages
        and (root / "tests").is_dir()
        and any((root / "tests").glob("test*.py"))
    ):
        languages, frameworks, commands = ["Python"], ["pytest"], ["python_pytest"]
    return ProjectProfile(
        primary_language=languages[0] if languages else "Unknown",
        manifests=manifests,
        test_frameworks=frameworks,
        default_test_commands=commands,
        src_layout=(root / "src").is_dir(),
    )
