"""
tests/test_dockerfile.py
------------------------
Regression tests for the production Docker image definition.
"""
from pathlib import Path


def test_dockerfile_copies_runtime_packages():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY core/ ./core/" in dockerfile
    assert "COPY src/ ./src/" not in dockerfile
