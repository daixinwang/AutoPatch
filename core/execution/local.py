"""Explicit opt-in only: the subprocess executes trusted repository code."""

import os
import subprocess
import sys
from pathlib import Path

from agent.models import TestCommandResult


def execute(argv, workspace, timeout, env=None):
    import threading

    # Drain pipes continuously, retaining at most 8 KB per stream in memory.
    def drain(pipe, result):
        head, tail, total = b"", b"", 0
        try:
            while True:
                block = pipe.read(4096)
                if not block:
                    break
                total += len(block)
                if len(head) < 4000:
                    take = min(4000 - len(head), len(block))
                    head += block[:take]
                    block = block[take:]
                tail = (tail + block)[-4000:]
        finally:
            pipe.close()
            result.append(
                (head + (b"\n[truncated]\n" if total > 8000 else b"") + tail).decode("utf-8", errors="replace")
            )

    try:
        proc = subprocess.Popen(
            argv,
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        return TestCommandResult(command=" ".join(argv), exit_code=None, status="unavailable", stderr_summary=str(exc))
    out, err = [], []
    workers = [
        threading.Thread(target=drain, args=(pipe, dest), daemon=True)
        for pipe, dest in [(proc.stdout, out), (proc.stderr, err)]
    ]
    for worker in workers:
        worker.start()
    try:
        code = proc.wait(timeout=max(1, min(timeout, 120)))
        status = "passed" if code == 0 else "failed"
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            proc.kill()
        else:
            import signal

            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        code, status = None, "timeout"
    for worker in workers:
        worker.join(timeout=2)
    return TestCommandResult(
        command=" ".join(argv),
        exit_code=code,
        status=status,
        stdout_summary=out[0] if out else "[output pipe still open]",
        stderr_summary=err[0] if err else "[output pipe still open]",
    )


class LocalTrustedBackend:
    def run(self, argv: list[str], workspace: Path, timeout: int = 120) -> TestCommandResult:
        argv = list(argv)
        if argv[0] == "python":
            argv[0] = sys.executable
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(workspace), str(Path(workspace) / "src")])
        return execute(argv, workspace, timeout, env)
