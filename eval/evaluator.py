"""
eval/evaluator.py
-----------------
单个 SWE-bench 实例的端到端评测编排。
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Dict, Optional

import logging

from eval.config import EvalConfig
from eval.dataset import SWEBenchInstance
from eval.instance_env import InstanceEnvironment, SetupError
from eval.verify import classify_result, run_tests

logger = logging.getLogger(__name__)


@dataclass
class InstanceResult:
    instance_id: str
    repo: str
    resolved: bool = False
    status: str = "error"  # resolved | partially_resolved | failed | error | timeout
    agent_patch: str = ""
    review_result: str = ""
    step_count: int = 0
    elapsed_seconds: float = 0.0
    fail_to_pass_results: Dict[str, bool] = field(default_factory=dict)
    pass_to_pass_results: Dict[str, bool] = field(default_factory=dict)
    error_message: Optional[str] = None
    baseline_valid: bool = True

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "repo": self.repo,
            "resolved": self.resolved,
            "status": self.status,
            "agent_patch": self.agent_patch,
            "review_result": self.review_result,
            "step_count": self.step_count,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "fail_to_pass_results": self.fail_to_pass_results,
            "pass_to_pass_results": self.pass_to_pass_results,
            "error_message": self.error_message,
            "baseline_valid": self.baseline_valid,
        }


class InstanceEvaluator:
    """评测单个 SWE-bench 实例。"""

    def __init__(self, instance: SWEBenchInstance, config: EvalConfig):
        self.instance = instance
        self.config = config

    def evaluate(self) -> InstanceResult:
        result = InstanceResult(
            instance_id=self.instance.instance_id,
            repo=self.instance.repo,
        )
        # Select environment and test runner based on config
        if self.config.use_docker:
            from eval.docker_env import DockerEnvironment
            from eval.verify import run_tests_docker
            env = DockerEnvironment(self.instance, self.config)
            def _run_tests(test_ids, ws, **kw):
                return run_tests_docker(
                    test_ids,
                    env.container_name,
                    ws,
                    container_path=env._container_path,
                    **kw,
                )
        else:
            env = InstanceEnvironment(self.instance, self.config)
            _run_tests = run_tests

        t0 = time.time()

        try:
            # 1. 搭建环境
            workspace = env.setup()
            workspace_str = str(workspace)

            # 2. 基线验证：FAIL_TO_PASS 应该失败
            if self.instance.fail_to_pass:
                baseline = _run_tests(
                    self.instance.fail_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 3,
                )
                baseline_all_fail = all(not v for v in baseline.values())
                result.baseline_valid = baseline_all_fail
                if not baseline_all_fail:
                    logger.warning(
                        "  [Eval] 基线验证未通过，跳过该实例"
                        "（可能是 Python 版本不兼容或环境问题）"
                    )
                    result.status = "error"
                    result.error_message = (
                        "baseline_invalid: FAIL_TO_PASS 测试在修复前已通过，"
                        "可能是 Python 版本不兼容（如 tomllib 需要 3.11+）或环境配置问题"
                    )
                    return result

            # 3. 运行 AutoPatch pipeline
            from autopatch import run_agent_on_issue
            agent_result = run_agent_on_issue(
                issue_text=self.instance.problem_statement,
                working_dir=workspace_str,
                repo_language="Python",
            )
            result.review_result = agent_result.get("review_result", "")
            result.step_count = agent_result.get("step_count", 0)

            # 4. 获取 Agent 生成的 diff，过滤掉 test_patch 引入的文件
            from core.diff_generator import generate_diff, filter_diff
            raw_diff = generate_diff(workspace_str)
            result.agent_patch = filter_diff(raw_diff, env.test_patch_files)

            # 5. 验证 FAIL_TO_PASS
            if self.instance.fail_to_pass:
                result.fail_to_pass_results = _run_tests(
                    self.instance.fail_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 2,
                )

            # 6. 验证 PASS_TO_PASS
            if self.instance.pass_to_pass:
                result.pass_to_pass_results = _run_tests(
                    self.instance.pass_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 2,
                )

            # 7. 分类结果
            result.status = classify_result(
                result.fail_to_pass_results,
                result.pass_to_pass_results,
            )
            result.resolved = result.status == "resolved"

        except SetupError as e:
            result.status = "error"
            result.error_message = f"环境搭建失败: {e}"
        except TimeoutError:
            result.status = "timeout"
            result.error_message = "评测超时"
        except Exception as e:
            result.status = "error"
            result.error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"
        finally:
            result.elapsed_seconds = time.time() - t0
            try:
                env.cleanup()
            except Exception:
                pass

        return result
