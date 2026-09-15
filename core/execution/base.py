from pathlib import Path
from typing import Protocol

from agent.models import TestCommandResult


class ExecutionBackend(Protocol):
    def run(self, argv: list[str], workspace: Path, timeout: int = 120) -> TestCommandResult: ...
