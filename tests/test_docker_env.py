"""
tests/test_docker_env.py
------------------------
Unit tests for eval/docker_env.py (pure logic only, no real Docker).
"""
from dataclasses import dataclass, field
from eval.docker_env import DockerEnvironment


@dataclass
class _FakeInstance:
    instance_id: str = "pallets__flask-4045"
    repo: str = "pallets/flask"
    test_patch: str = ""
    fail_to_pass: list = field(default_factory=list)
    pass_to_pass: list = field(default_factory=list)


@dataclass
class _FakeConfig:
    docker_image_prefix: str = "swebench/sweb.eval.x86_64"
    keep_image: bool = False
    workdir_base: str = "/tmp/autopatch_test"


class TestDockerEnvironmentProperties:
    def _make_env(self, instance_id="pallets__flask-4045"):
        inst = _FakeInstance(instance_id=instance_id)
        cfg = _FakeConfig()
        return DockerEnvironment(inst, cfg)

    def test_image_name_default_prefix(self):
        env = self._make_env()
        assert env.image_name == "swebench/sweb.eval.x86_64.pallets__flask-4045:latest"

    def test_image_name_custom_prefix(self):
        inst = _FakeInstance()
        cfg = _FakeConfig(docker_image_prefix="myrepo/images")
        env = DockerEnvironment(inst, cfg)
        assert env.image_name == "myrepo/images.pallets__flask-4045:latest"

    def test_container_name(self):
        env = self._make_env()
        assert env.container_name == "autopatch_pallets__flask-4045"

    def test_container_name_with_underscores(self):
        env = self._make_env("sympy__sympy-20154")
        assert env.container_name == "autopatch_sympy__sympy-20154"
