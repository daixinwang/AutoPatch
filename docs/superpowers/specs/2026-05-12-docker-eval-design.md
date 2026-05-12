# Docker-Based SWE-bench Evaluation Design

Date: 2026-05-12
Status: Approved

## Background

当前 `eval/instance_env.py` 使用 `git clone + pip install -e .` 搭建评测环境，会安装最新版依赖，导致历史版本的 repo 出现依赖冲突（如 Flask 旧版本 + 新版 werkzeug，或 requests 旧版本 + 新版 urllib3）。SWE-bench 官方评测使用 per-instance Docker 镜像，每个镜像内已预装精确锁定的依赖版本。

## 目标

在不改动 Agent pipeline 的前提下，将 eval 框架的环境搭建和测试执行切换为 Docker 模式，消除依赖版本冲突。

## 方案：Agent 在宿主机跑，Docker 只负责测试执行

Docker 只插入两个点：
1. **环境搭建**：`docker pull` + `docker run` + `docker cp /testbed → 本地`，替换原有的 `git clone + pip install`
2. **测试执行**：`docker cp 本地改动 → 容器` + `docker exec pytest`，替换本地 subprocess pytest

Agent 所有文件操作（`read_file`、`edit_file`、`verify_importable`）继续读写本地目录，无感知 Docker。

## 架构

### 新增/修改文件

| 文件 | 操作 | 职责 |
|---|---|---|
| `eval/docker_env.py` | 新建 | `DockerEnvironment` 类，镜像 `InstanceEnvironment` 接口 |
| `eval/config.py` | 修改 | 新增 `use_docker: bool`、`docker_image_prefix: str`、`keep_image: bool` |
| `eval/evaluator.py` | 修改 | 按 `use_docker` 选择 env 类型和测试执行函数 |
| `eval/verify.py` | 修改 | 新增 `run_tests_docker()` 函数 |
| `run_eval.py` | 修改 | 新增 `--docker` CLI 参数 |

### Docker 镜像命名规则

SWE-bench 官方格式：

```
swebench/sweb.eval.x86_64.<instance_id>:latest
# 例：swebench/sweb.eval.x86_64.pallets__flask-4045:latest
```

`docker_image_prefix` 默认值为 `swebench/sweb.eval.x86_64`，支持通过环境变量覆盖。

## 数据流

每个 instance 的完整生命周期：

```
docker pull swebench/sweb.eval.x86_64.<instance_id>:latest
        ↓
docker run -d --name autopatch_<instance_id> <image> sleep infinity
        ↓
docker cp <container>:/testbed → /tmp/autopatch_eval/workspaces/<instance_id>/
（备选路径：/repo）
        ↓
本地 git apply test_patch，记录 test_patch_files（同现有逻辑）
        ↓
[基线验证] docker cp + docker exec pytest <FAIL_TO_PASS>
        ↓
AutoPatch Agent 运行（读写本地文件）
        ↓
[FAIL_TO_PASS 验证] docker cp + docker exec pytest
[PASS_TO_PASS 验证] docker cp + docker exec pytest
        ↓
docker stop + docker rm（清理容器）
docker rmi（keep_image=False 时执行）
rm -rf 本地工作目录
```

## 接口设计

### DockerEnvironment

```python
class DockerEnvironment:
    workspace: Path           # 本地工作目录（Agent 直接操作）
    test_patch_files: Set[str]  # test_patch 修改的文件（用于 diff 过滤）
    container_name: str       # 容器名（供 run_tests_docker 使用）

    def setup(self) -> Path: ...    # pull + run + cp + apply patch
    def cleanup(self) -> None: ...  # stop + rm + rmi + rm workspace
```

容器名格式：`autopatch_<instance_id>`（支持 `docker rm -f autopatch_*` 批量清理）

### run_tests_docker()

```python
def run_tests_docker(
    test_ids: List[str],
    container_name: str,
    workspace: str,
    repo: str = "",
    timeout: int = 300,
) -> Dict[str, bool]:
    # 1. docker cp <workspace>/. <container>:/testbed/
    # 2. docker exec <container> bash -c "cd /testbed && python -m pytest -xvs <tests>"
    # 3. 复用 _parse_pytest_output() 解析结果
```

### evaluator.py 选择逻辑

```python
if self.config.use_docker:
    env = DockerEnvironment(self.instance, self.config)
    _run_tests = lambda ids, ws, **kw: run_tests_docker(ids, env.container_name, ws, **kw)
else:
    env = InstanceEnvironment(self.instance, self.config)
    _run_tests = run_tests
```

## 错误处理

| 错误场景 | 处理方式 |
|---|---|
| `docker pull` 失败（镜像不存在/网络） | `result.status = "error"`，`error_message` 包含镜像名，直接返回 |
| `/testbed` 路径不存在 | 顺序尝试 `/testbed`、`/repo`，都失败则 `SetupError` |
| `docker exec pytest` 超时 | 返回全部 `False`，容器继续存活 |
| 容器泄漏 | `cleanup()` 在 `finally` 中调用；容器名前缀 `autopatch_` 支持手动批量清理 |

## 配置

新增 config 字段：

```python
use_docker: bool = False              # 开启 Docker 模式
docker_image_prefix: str = "swebench/sweb.eval.x86_64"
keep_image: bool = False              # True 时不删除镜像（节省重复拉取时间）
```

CLI 新增参数：`--docker`（开启 Docker 模式）、`--keep-image`（保留镜像）

## 使用方式

```bash
# 安装 Docker Desktop 后：
python run_eval.py --instance-ids pallets__flask-4045 --docker

# 保留镜像（跑多个同 repo 的 instance 时节省拉取时间）
python run_eval.py --repos pallets/flask --max-instances 3 --docker --keep-image
```

## 向后兼容

不加 `--docker` 参数时行为完全不变，原有 `InstanceEnvironment` 路径不受影响。

## 已知限制

**`verify_importable` 在 Docker 模式下可能误报**：该工具在宿主机 Python 环境中验证模块导入，而 Docker 模式下宿主机未安装目标 repo 的依赖（如 Flask）。因此 Coder 调用 `verify_importable` 时可能收到 `[失败]`，即使代码本身正确。这属于误报而非漏报，Reviewer 仍以 TestRunner（在 Docker 内运行）的实际结果为准。后续可扩展为通过 `docker exec` 在容器内运行 import 检查。
