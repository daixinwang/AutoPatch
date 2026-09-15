"""Private local clone preserving the caller's checkout and uncommitted edits."""

import os
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


def remove_workspace(path):
    def retry(func, name, exc):
        os.chmod(name, stat.S_IWRITE)
        func(name)

    shutil.rmtree(path, onerror=retry)


@contextmanager
def isolated_workspace(source, keep=False):
    target = Path(tempfile.mkdtemp(prefix="autopatch_local_"))
    try:
        subprocess.run(
            ["git", "clone", "--no-hardlinks", "--", str(Path(source).resolve()), str(target)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        yield target
    finally:
        if not keep:
            remove_workspace(target)
