# sanity-v1 评测计划

## 目标

`sanity-v1` 是 AutoPatch 新评测协议的第一组本地 sanity benchmark。它不用于证明模型能力高低，而是用于验证评测链路是否稳定：

1. 能读取 case 元数据。
2. 能从 fixture 创建临时 workspace。
3. 能生成或记录 `base_commit`。
4. 能运行 baseline validation。
5. 能运行 agent 或 mock patch。
6. 能验证 patch。
7. 能产出 `verdict.json`、`patch.diff`、`test-before.log`、`test-after.log` 等协议要求产物。

之前零散评测结果不纳入本组 benchmark。

## 数据目录

```text
eval/cases/sanity-v1/
  py-single-file.json
  py-multi-file.json
  py-test-modification-guard.json
  py-regression-risk.json
  invalid-baseline.json

eval/fixtures/sanity-v1/
  py-single-file/
  py-multi-file/
  py-test-modification-guard/
  py-regression-risk/
  invalid-baseline/
```

Fixture 以普通目录提交，不在仓库中嵌套 `.git`。后续 sanity runner 应复制 fixture 到临时目录，并在临时目录内执行：

```bash
git init
git add .
git commit -m "baseline"
```

生成的 commit sha 写入本次 run 的 `workspace-info.json`，并作为 case 的实际 `base_commit`。

## Case 设计

| Case | 目的 | Baseline 预期 | 正确 patch 预期 | Verdict 目标 |
|---|---|---|---|---|
| `py-single-file` | 验证最小单文件 bug 修复链路 | F2P 失败，P2P 通过 | 修改 `autopatch_demo/calculator.py` 的折扣计算 | `resolved` |
| `py-multi-file` | 验证跨文件定位和调用链 | F2P 失败，P2P 通过 | 修改 `shop/pricing.py` 的税费计算 | `resolved` |
| `py-test-modification-guard` | 验证测试文件修改拒绝逻辑 | F2P 失败，P2P 通过 | 应修改源码；如果修改测试，判失败 | `resolved` 或 `failed/test_modification` |
| `py-regression-risk` | 验证 PASS_TO_PASS 能捕获回归 | F2P 失败，P2P 通过 | 修复空白归一化，同时保留标点 | `resolved`；错误 patch 可触发 `partial/regression` |
| `invalid-baseline` | 验证 invalid_case 分类 | F2P 在 baseline 已通过 | 不应运行 agent | `invalid_case` |

## 执行策略

第一阶段只要求 runner 能完成 baseline validation 和产物目录初始化，不要求接入真实大模型。建议支持两种模式：

- `--baseline-only`：只跑 baseline，验证 `invalid_case` 和 `infra_error` 分类。
- `--mock-patch-dir`：从固定 patch 目录读取 patch，用于验证 patch validation 和 verdict 分类。

第二阶段再接入 AutoPatch agent。此时每个 case 运行后必须保存完整 trace。

## 测试命令

每个 fixture 都是最小 Python 项目，测试命令统一使用：

```bash
python -m pytest -q
```

单个 selector 由 case JSON 中的 `fail_to_pass` 和 `pass_to_pass` 字段提供。

## Baseline-only 运行命令

最小 sanity runner 先只做 baseline validation，不调用真实 agent：

```bash
python -m eval.sanity \
  --baseline-only \
  --cases-dir eval/cases/sanity-v1 \
  --results-dir eval/results \
  --run-id sanity-v1-baseline
```

该命令应生成：

```text
eval/results/sanity-v1-baseline/
  config.json
  report.json
  report.md
  cases/<case_id>/
    case.json
    issue.md
    test-before.log
    verdict.json
    workspace-info.json
```

## Mock patch 运行命令

Patch validation 阶段使用固定 patch 文件验证判定链路，不调用真实 agent：

```bash
python -m eval.sanity \
  --cases-dir eval/cases/sanity-v1 \
  --results-dir eval/results \
  --run-id sanity-v1-mock-resolved \
  --mock-patch-dir eval/mock_patches/sanity-v1/resolved
```

Mock patch 目录约定为 `<case_id>.diff`。例如：

```text
eval/mock_patches/sanity-v1/resolved/py-single-file.diff
eval/mock_patches/sanity-v1/test-modification/py-test-modification-guard.diff
eval/mock_patches/sanity-v1/regression/py-regression-risk.diff
eval/mock_patches/sanity-v1/patch-apply-failure/py-single-file.diff
```

Resolved patch 集的期望聚合结果：

- `resolved`: 4
- `invalid_case`: 1
- `failed`: 0
- `partial`: 0

## 真实 agent 运行命令

确认 baseline 和 mock patch 链路稳定后，再运行真实 AutoPatch agent。建议先只跑一个最小 case：

```bash
python -m eval.sanity \
  --agent \
  --case-ids py-single-file \
  --cases-dir eval/cases/sanity-v1 \
  --results-dir eval/results \
  --run-id sanity-v1-agent-py-single-file
```

真实 agent 模式会：

1. 复制 fixture 并初始化 baseline commit。
2. 执行 baseline validation。
3. 如果 case 不是 `baseline_ready`，跳过 agent。
4. 调用 `autopatch.run_agent_on_issue(issue_text, workspace, repo_language)`。
5. 从 workspace 生成 `patch.diff`。
6. 生成 `changed-files.json`。
7. 运行 patch 后的 F2P/P2P 测试。
8. 写入最终 `verdict.json` 和 `trace.jsonl`。

运行真实 agent 前需要配置项目正常运行所需的模型环境变量，例如 `OPENAI_API_KEY`、模型名和可选的 embedding 配置。`invalid-baseline` 这类 baseline 无效 case 会跳过 agent，因此可用于不触发模型调用的 CLI smoke test：

```bash
python -m eval.sanity \
  --agent \
  --case-ids invalid-baseline \
  --cases-dir eval/cases/sanity-v1 \
  --results-dir /tmp/autopatch-sanity-agent-results \
  --run-id invalid-smoke
```

## 成功标准

完成 sanity-v1 harness 后，至少应满足：

- 5 个 case 都能生成 `eval/results/<run_id>/cases/<case_id>/`。
- `invalid-baseline` 不运行 agent，直接产出 `invalid_case`。
- 其它 4 个 case 的 baseline 满足：F2P 失败，P2P 通过。
- 任意 test 文件变更能被识别并反映到 `verdict.json`。
- 报告同时包含 all-case 和 valid-case resolved rate。
