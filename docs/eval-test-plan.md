# AutoPatch SWE-bench Lite 测试计划

> 更新日期：2026-05-13

## 背景

已完成：
- Docker 评测框架接入，依赖版本冲突问题消除
- `pallets__flask-4045` 评测结果：`partially_resolved`（1/2 FAIL_TO_PASS 通过）

下一步：选取难度适中的 SWE-bench Lite instance 系统评测，验证 Agent 的真实 resolve rate。

---

## 选例策略

筛选标准（按优先级）：
1. `FAIL_TO_PASS` 数量少（1-2 个）
2. `PASS_TO_PASS` 数量少（P2P 越少，回归影响面越小）
3. `problem_statement` 简短清晰（问题描述越短，意图越明确）
4. 非 sympy/sympy（纯数学推导类，模型推理负担重）
5. 代码库结构简单（requests/pylint/pytest 优于 django/scikit-learn）

---

## Tier 1：高置信候选（推荐优先跑）

| Instance ID | 仓库 | F2P | P2P | 描述摘要 | 预期难度 |
|---|---|---|---|---|---|
| `pylint-dev__pylint-5859` | pylint | 1 | 10 | `--notes` 选项忽略纯标点的 note tag | 低 |
| `pytest-dev__pytest-7432` | pytest | 1 | 77 | `--runxfail` 破坏 skip 位置报告 | 低 |
| `pytest-dev__pytest-7373` | pytest | 1 | 81 | skipif/xfail 字符串条件缓存错误 | 低 |
| `psf__requests-3362` | requests | 1 | 75 | `iter_content(decode_unicode=True)` 返回 bytes | 低 |
| `pylint-dev__pylint-7993` | pylint | 1 | 10 | 自定义 braces 在 message template 不生效 | 低-中 |

**推荐理由**：
- 均为 1 个 FAIL_TO_PASS，修复验证明确
- pylint/pytest/requests 代码库结构清晰，依赖简单
- 都是典型的"一处代码的小 bug fix"，Agent 能定位修复

---

## Tier 2：中等置信候选

| Instance ID | 仓库 | F2P | P2P | 描述摘要 | 预期难度 |
|---|---|---|---|---|---|
| `pytest-dev__pytest-6116` | pytest | 2 | 69 | `--collect-only` 需要单字符缩写 | 低-中 |
| `pytest-dev__pytest-5495` | pytest | 2 | 86 | byte strings 断言提示混乱 | 中 |
| `pylint-dev__pylint-6506` | pylint | 2 | 6 | 未知选项时打印 traceback 而非友好错误 | 中 |
| `pytest-dev__pytest-8365` | pytest | 1 | 32 | 用户名含非法字符时 tmpdir 创建失败 | 中 |
| `pytest-dev__pytest-5221` | pytest | 2 | 170 | `--fixtures` 应显示 fixture scope | 中 |

---

## Tier 3：备选（有环境或推理挑战）

| Instance ID | 仓库 | F2P | P2P | 描述摘要 | 挑战 |
|---|---|---|---|---|---|
| `pallets__flask-4045` | flask | 2 | 50 | Blueprint 名称含点号应报错 | 已跑，partially_resolved |
| `pallets__flask-5063` | flask | 2 | 54 | flask routes 显示 domain 信息 | ARM64 模拟 |
| `pydata__xarray-4248` | xarray | 1 | 18 | dataset overview 显示 units | 依赖较多 |

---

## 建议执行顺序

```bash
# 阶段 1：Tier 1 全跑，每次单 instance，观察 resolve rate
python run_eval.py --instance-ids pylint-dev__pylint-5859 --docker --keep-image
python run_eval.py --instance-ids pytest-dev__pytest-7432 --docker --keep-image
python run_eval.py --instance-ids pytest-dev__pytest-7373 --docker --keep-image
python run_eval.py --instance-ids psf__requests-3362 --docker --keep-image
python run_eval.py --instance-ids pylint-dev__pylint-7993 --docker --keep-image

# 阶段 2：如果 Tier 1 有 ≥ 2 个 resolved，扩大到 Tier 2
python run_eval.py \
  --instance-ids pytest-dev__pytest-6116 pytest-dev__pytest-5495 pylint-dev__pylint-6506 \
  --docker --keep-image

# 阶段 3：汇总结果，计算 resolve rate
cat eval/results/*/report.json
```

---

## 预镜像拉取（节省评测时间）

建议提前拉取 Tier 1 的镜像：

```bash
docker pull swebench/sweb.eval.x86_64.pylint-dev_1776_pylint-5859:latest &
docker pull swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-7432:latest &
docker pull swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-7373:latest &
docker pull swebench/sweb.eval.x86_64.psf_1776_requests-3362:latest &
docker pull swebench/sweb.eval.x86_64.pylint-dev_1776_pylint-7993:latest &
wait && echo "所有镜像拉取完成"
```

---

## 成功指标

| 阶段 | 目标 |
|---|---|
| Tier 1（5 个）| resolve rate ≥ 40%（≥ 2 个 resolved） |
| Tier 1+2（10 个）| resolve rate ≥ 30% |
| 全量 SWE-bench Lite（300 个）| resolve rate ≥ 5%（业界参考：多数开源 agent 5-20%） |

---

## 已知限制

| 问题 | 影响 | 状态 |
|---|---|---|
| x86_64 镜像在 ARM64 Mac 上通过 Rosetta 模拟运行 | 部分 PASS_TO_PASS 测试可能失败（非 Agent 导致）| 待确认 |
| `verify_importable` 在 Docker 模式下误报失败 | Coder 可能收到误导性反馈 | 已知，Reviewer 以 TestRunner 为准 |
| docker pull 超时（单镜像 >10 分钟）| 需提前拉取 | 已规避（提前 pull） |
