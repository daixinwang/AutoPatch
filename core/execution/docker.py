"""Ephemeral resource-limited containers. No credentials or Docker socket mounted.

The SWE-bench environment's image lifecycle remains in eval/docker_env.py;
this backend uses the same Docker CLI without its trusted setup/sync operations.
"""

import subprocess
import uuid
from pathlib import Path

from core.execution.local import execute


class DockerSandboxBackend:
    def __init__(self, image: str, python_executable: str | None = None, container_workspace: str = "/workspace"):
        if not image or image.startswith("-"):
            raise ValueError("Invalid sandbox image")
        if container_workspace not in ("/workspace", "/testbed", "/repo"):
            raise ValueError("Unsupported container workspace")
        self.image = image
        self.python_executable = python_executable
        self.container_workspace = container_workspace

    def command(self, argv: list[str], workspace: Path, name: str) -> list[str]:
        root = str(Path(workspace).resolve())
        if "," in root:
            raise ValueError("Docker mount paths cannot contain commas")
        target = self.container_workspace
        argv = list(argv)
        if argv and argv[0] == "python" and self.python_executable:
            argv[0] = self.python_executable
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--pull",
            "never",
            "--network",
            "none",
            "--log-driver",
            "none",
            "--cpus",
            "2",
            "--memory",
            "1g",
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,size=256m",
            "--tmpfs",
            f"{target}:rw,nosuid,size=512m,mode=1777",
            "--user",
            "65534:65534",
            "--mount",
            f"type=bind,source={root},target=/input,readonly",
            "--workdir",
            target,
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            f"PYTHONPATH={target}:{target}/src",
            "--env",
            "HOME=/tmp",
            "--env",
            "GOCACHE=/tmp/go-cache",
            "--env",
            "GRADLE_USER_HOME=/tmp/gradle",
            "--entrypoint",
            "/bin/sh",
            self.image,
            "-c",
            'cp -R /input/. "$PWD/" && exec "$@"',
            "autopatch",
            *argv,
        ]

    def run(self, argv, workspace, timeout=120):
        name = "autopatch-test-" + uuid.uuid4().hex
        try:
            result = execute(self.command(argv, workspace, name), workspace, timeout)
            result.command = " ".join(argv)
            if result.exit_code in (125, 126, 127):
                result.status = "unavailable"
            return result
        finally:
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
