"""Execution backends for trusted fixtures and untrusted repositories."""

import os

from core.execution.docker import DockerSandboxBackend
from core.execution.local import LocalTrustedBackend


def get_backend():
    name = os.getenv("AUTOPATCH_EXECUTION_BACKEND", "docker")
    if name == "local":
        return LocalTrustedBackend()
    if name == "docker":
        return DockerSandboxBackend(os.getenv("AUTOPATCH_SANDBOX_IMAGE", "autopatch-sandbox:latest"))
    raise ValueError(f"Unknown execution backend: {name}")
