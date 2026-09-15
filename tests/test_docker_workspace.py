import os
from pathlib import Path

from agent.models import TestCommandResult as CommandResult
from core.execution.docker import DockerSandboxBackend


def test_container_reads_separate_snapshot_without_changing_private_source(tmp_path, monkeypatch):
    from core.execution import docker

    source = tmp_path / "private"
    source.mkdir(mode=0o700)
    (source / "source.py").write_text("value = 1\n")
    (source / "source.py").chmod(0o600)
    before = source.stat().st_mode
    seen = []

    def run(command, workspace, timeout):
        mount = command[command.index("--mount") + 1]
        snapshot = Path(mount.split("source=", 1)[1].split(",target=", 1)[0])
        seen.append(snapshot)
        assert snapshot != source
        assert (snapshot / "source.py").read_text() == "value = 1\n"
        if os.name == "posix":
            assert snapshot.stat().st_mode & 0o005 == 0o005
            assert (snapshot / "source.py").stat().st_mode & 0o004
        return CommandResult(command="test", exit_code=0, status="passed")

    monkeypatch.setattr(docker, "execute", run)
    monkeypatch.setattr(docker.subprocess, "run", lambda *a, **kw: None)
    result = DockerSandboxBackend("image:test").run(["python", "source.py"], source)
    assert result.status == "passed"
    assert source.stat().st_mode == before
    assert all(not path.exists() for path in seen)
