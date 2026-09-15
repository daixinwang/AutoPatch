"""Ephemeral resource-limited containers. No credentials or Docker socket mounted.

The SWE-bench environment's image lifecycle remains in eval/docker_env.py;
this backend uses the same Docker CLI without its trusted setup/sync operations.
"""

import shutil
import stat
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from core.execution.local import execute
from core.local_workspace import remove_workspace


@contextmanager
def readable_snapshot(workspace):
    """Copy private host files for an unprivileged container; never chmod source."""
    snapshot = Path(tempfile.mkdtemp(prefix="autopatch_input_"))
    try:
        shutil.copytree(workspace, snapshot, dirs_exist_ok=True, symlinks=True)
        for path in [snapshot, *snapshot.rglob("*")]:
            if path.is_symlink():
                continue
            mode = path.stat().st_mode
            path.chmod(0o755 if path.is_dir() else 0o644 | (stat.S_IMODE(mode) & 0o111))
        yield snapshot
    finally:
        remove_workspace(snapshot)


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
            with readable_snapshot(workspace) as snapshot:
                result = execute(self.command(argv, snapshot, name), workspace, timeout)
            result.command = " ".join(argv)
            if result.exit_code in (125, 126, 127):
                result.status = "unavailable"
            return result
        finally:
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
