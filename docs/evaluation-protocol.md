# AutoPatch 评测协议

> 状态：所有新评测的基准协议。
> 之前零散、临时的评测结果不纳入本协议下生成的报告。

## 推荐入口

新的统一评测入口是：

```bash
python -m eval.unified --dataset sanity-v1 --mode baseline-only
python -m eval.unified --dataset sanity-v2 --mode agent
python -m eval.unified --dataset swebench-smoke --mode agent
python -m eval.unified --dataset swebench-lite --mode agent --instance-ids <instance_id>
```

`python -m eval.sanity` 和 `python run_eval.py` 仍保留为兼容入口；新评测结果应优先使用 `eval.unified` 产物目录和 verdict 定义。

## 目标

用可复现、可审计的方式评测 AutoPatch 作为 coding agent 的能力。每一条被汇报的结果都必须回答三个问题：

1. 这个结果由哪个代码版本、模型配置、数据集 case 和运行环境产生？
2. Agent 生成的 patch 是否能干净应用，并通过要求的测试？
3. 如果失败，失败原因来自 agent、评测框架，还是运行环境？

## 适用范围

本协议适用于：

- 本地 sanity benchmark
- 人工整理的真实 GitHub issue benchmark
- SWE-bench 或 SWE-bench 风格 benchmark
- `no_rag`、`no_reviewer`、`grep_only` 等消融实验

本协议不定义 prompt 策略、case 筛选策略或模型选择策略。每次具体评测应另行说明这些内容。

## Run 元数据

每次评测 run 必须保存 `config.json`，字段如下：

```json
{
  "protocol_version": "2026-06-14",
  "run_id": "2026-06-14T19-30-00Z-full",
  "autopatch_commit": "<git commit sha>",
  "autopatch_dirty": false,
  "dataset_name": "sanity-v1",
  "dataset_version": "2026-06-14",
  "case_ids": ["case-001"],
  "agent_config": {
    "mode": "full",
    "planner_model": "claude-haiku-4-5-20251001",
    "coder_model": "claude-sonnet-4-6",
    "test_runner_model": "claude-haiku-4-5-20251001",
    "reviewer_model": "claude-sonnet-4-6",
    "temperature": 0,
    "max_review_retries": 3,
    "max_coder_steps": 40,
    "rag_enabled": true,
    "reviewer_enabled": true
  },
  "environment": {
    "os": "macOS",
    "architecture": "arm64",
    "python_version": "3.12.x",
    "node_version": "20.x",
    "docker_enabled": true,
    "docker_platform": "linux/amd64"
  },
  "timeouts": {
    "agent_seconds": 900,
    "test_seconds": 300,
    "case_seconds": 1800
  }
}
```

如果某个字段未知，记录为 `null`，不要省略字段。

## Case 元数据

每个 benchmark case 都必须有稳定的 case 文件，建议放在 `eval/cases/<dataset>/<case_id>.json`。

必需字段：

```json
{
  "case_id": "case-001",
  "source": "local_sanity | github_issue | swe_bench",
  "repo": "owner/repo",
  "base_commit": "<commit sha>",
  "issue_number": 42,
  "issue_url": "https://github.com/owner/repo/issues/42",
  "issue_title": "Bug title",
  "issue_body": "Full issue body used as agent input.",
  "language": "Python",
  "difficulty": "easy | medium | hard",
  "fail_to_pass": ["tests/test_bug.py::test_fixed_behavior"],
  "pass_to_pass": ["tests/test_existing.py"],
  "expected_files": ["src/module.py"],
  "notes": "Any evaluator-only notes. Do not pass this field to the agent."
}
```

规则：

- `issue_body` 是传给 agent 的 issue 主体，除非 case 明确包含评论，否则不要追加其它信息。
- `expected_files` 只供评测者分析使用，不能传给 agent。
- `base_commit` 必须是不可变 commit sha，不能用分支名。
- 测试应尽量写成可直接执行的 selector。

## 输出目录结构

每次 run 写入：

```text
eval/results/<run_id>/
  config.json
  report.json
  report.md
  cases/
    <case_id>/
      case.json
      issue.md
      trace.jsonl
      patch.diff
      changed-files.json
      test-before.log
      test-after.log
      verdict.json
      workspace-info.json
```

必需产物：

- `case.json`：本次 run 实际使用的 case 元数据。
- `issue.md`：实际传给 agent 的 issue prompt。
- `trace.jsonl`：按时间顺序记录的结构化 agent 事件。
- `patch.diff`：agent 生成的 patch，已过滤评测专用 test patch。
- `changed-files.json`：变更文件列表，并标记 source/test/generated 等类型。
- `test-before.log`：运行 agent 前的 baseline 测试输出。
- `test-after.log`：应用 patch 后的验证测试输出。
- `verdict.json`：最终机器可读判定。
- `workspace-info.json`：仓库路径、base commit、最终 diff 状态、Docker image 等信息。

## Trace 格式

`trace.jsonl` 每行一个 JSON 对象。至少支持这些事件类型：

```json
{"ts": "2026-06-14T19:30:00Z", "type": "case_started", "case_id": "case-001"}
{"ts": "2026-06-14T19:30:10Z", "type": "node_started", "node": "planner"}
{"ts": "2026-06-14T19:30:20Z", "type": "tool_call", "node": "coder", "tool": "read_file", "args_summary": {"file_path": "src/module.py"}}
{"ts": "2026-06-14T19:30:22Z", "type": "tool_result", "node": "coder", "tool": "read_file", "status": "ok", "output_chars": 4821}
{"ts": "2026-06-14T19:31:00Z", "type": "node_finished", "node": "coder", "elapsed_ms": 40000}
{"ts": "2026-06-14T19:35:00Z", "type": "case_finished", "case_id": "case-001", "verdict": "resolved"}
```

Trace 规则：

- 不记录 secret 或原始 API key。
- 不要求在 trace 中保存完整文件内容；完整修改以 `patch.diff` 为准。
- 工具失败必须记录成结构化事件，不能只存在于自由文本日志里。
- 如果并发执行 case，每个事件都应包含 `case_id`。

## Verdict 定义

每个 case 的最终 verdict 必须是以下之一：

- `resolved`
- `partial`
- `failed`
- `agent_timeout`
- `infra_error`
- `invalid_case`

### resolved

只有满足全部条件时才能判为 `resolved`：

- Agent 生成了非空 patch。
- Patch 能干净应用到目标 `base_commit`。
- 没有修改禁止修改的测试文件，除非该 benchmark 明确允许生成测试。
- 应用 patch 后，所有 `FAIL_TO_PASS` 测试通过。
- 应用 patch 后，所有 `PASS_TO_PASS` 测试通过。
- 没有无法解释的非零退出验证命令。

### partial

满足全部条件时判为 `partial`：

- Patch 能干净应用。
- 没有修改禁止修改的测试文件。
- 所有 `FAIL_TO_PASS` 测试通过。
- 至少一个 `PASS_TO_PASS` 测试失败。
- 该失败不能被归类为基础设施噪声。

### failed

Case 正常运行，但 agent 没有解决问题时判为 `failed`。典型情况：

- Agent 没有生成 patch。
- Patch 不能干净应用。
- 修改了禁止修改的测试文件。
- 任意 `FAIL_TO_PASS` 测试在 patch 后仍失败。
- Patch 引入语法错误或 import 错误。
- Agent 修错了行为。

### agent_timeout

评测环境健康，但 agent 超过配置的 case 或 agent timeout 时，判为 `agent_timeout`。

### infra_error

由于评测框架或运行环境失败，导致无法判断 agent 表现时，判为 `infra_error`。典型情况：

- Docker image 无法拉取或启动。
- Baseline 测试前依赖安装失败。
- 因网络问题无法 clone 仓库。
- Baseline 测试因环境问题无法运行，且与目标 bug 无关。
- 评测框架在产出 patch verdict 前崩溃。

基础设施失败不能直接计入 agent failure。报告中必须同时展示：

- `resolved_rate_all = resolved / total_cases`
- `resolved_rate_valid = resolved / (total_cases - infra_error - invalid_case)`

### invalid_case

Case 定义本身错误时，判为 `invalid_case`。典型情况：

- `base_commit` 不存在。
- `FAIL_TO_PASS` 测试在 patch 前已经通过。
- 必需测试 selector 不存在。
- Issue 元数据指向了错误仓库。

发布 benchmark 结果前，`invalid_case` 必须被修正或移除。

## Baseline Validation

运行 agent 前：

1. Checkout `base_commit`。
2. 运行所有 `FAIL_TO_PASS` selector。
3. 运行所有 `PASS_TO_PASS` selector。
4. 保存输出到 `test-before.log`。

期望 baseline：

- 所有 `FAIL_TO_PASS` 测试在 patch 前失败。
- 所有 `PASS_TO_PASS` 测试在 patch 前通过。

如果不满足：

- selector 或元数据错误时，标记 `invalid_case`。
- 依赖或环境问题导致时，标记 `infra_error`。
- 不要继续运行该 case 的 agent。

## Patch Validation

Agent 结束后：

1. 保存仓库原始 diff 到 `patch.diff`。
2. 在 fresh checkout 的 `base_commit` 上验证 patch 能否干净应用。
3. 检测变更文件并保存 `changed-files.json`。
4. 拒绝禁止的测试文件修改。
5. 运行 `FAIL_TO_PASS`。
6. 运行 `PASS_TO_PASS`。
7. 保存输出到 `test-after.log`。
8. 写入 `verdict.json`。

`verdict.json` 格式：

```json
{
  "case_id": "case-001",
  "verdict": "resolved",
  "reason": "FAIL_TO_PASS and PASS_TO_PASS passed after patch.",
  "patch_applies": true,
  "modified_test_files": false,
  "fail_to_pass": {
    "total": 1,
    "passed": 1,
    "failed": []
  },
  "pass_to_pass": {
    "total": 5,
    "passed": 5,
    "failed": []
  },
  "timing": {
    "agent_seconds": 210.4,
    "verification_seconds": 38.1
  }
}
```

## 测试文件修改策略

默认策略：禁止修改测试文件。

满足任一条件即视为测试文件：

- 位于 `tests/`、`test/`、`spec/` 或 `__tests__/` 目录下。
- 文件名以 `test_` 开头。
- 文件名以 `_test.py`、`.test.ts`、`.test.tsx`、`.spec.ts` 或 `.spec.tsx` 结尾。

如果某个 benchmark 明确要求添加测试，case 必须设置：

```json
{
  "allow_test_modifications": true
}
```

这类 case 必须和 bug-fix-only case 分开汇报。

## 消融模式

至少支持这些评测模式：

| 模式 | 说明 |
|---|---|
| `full` | Planner + Coder + tools + RAG + TestRunner + Reviewer retry |
| `no_rag` | 与 full 相同，但关闭 semantic search |
| `no_reviewer` | 与 full 相同，但关闭 Reviewer retry |
| `grep_only` | 关闭 semantic search，只保留精确/正则检索工具 |
| `single_pass` | 第一次 patch 尝试后不允许 retry |

比较不同模式时，必须使用相同 case 集和 timeout 策略。

## 报告指标

每份聚合报告必须包含：

- Total cases
- Valid cases
- `resolved`
- `partial`
- `failed`
- `agent_timeout`
- `infra_error`
- `invalid_case`
- `resolved_rate_all`
- `resolved_rate_valid`
- 平均 agent 运行时间
- agent 运行时间中位数
- 平均 step count
- 平均工具调用次数
- 平均变更文件数量

推荐报告表：

| Mode | Total | Valid | Resolved | Partial | Failed | Agent Timeout | Infra Error | Valid Resolve Rate | Avg Time | Avg Tool Calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full | 10 | 10 | 3 | 2 | 5 | 0 | 0 | 30.0% | 240s | 18.4 |

## 失败分类

每个非 resolved 的有效 case 必须分配一个主要失败类别：

- `localization_failure`：agent 没有定位到相关代码。
- `wrong_fix`：agent 找到了相关代码，但实现了错误行为。
- `incomplete_fix`：patch 只处理了部分要求。
- `regression`：`FAIL_TO_PASS` 通过，但 `PASS_TO_PASS` 失败。
- `syntax_or_import_error`：patch 破坏语法或 import。
- `test_modification`：patch 修改了禁止修改的测试文件。
- `patch_apply_failure`：生成的 diff 无法干净应用。
- `tool_failure`：内部工具行为误导或阻塞了 agent。
- `reviewer_failure`：Reviewer 接受了错误 patch，或拒绝了正确 patch。
- `timeout`：环境有效，但 agent 没有在限定时间内完成。

失败分析必须引用 `trace.jsonl`、`patch.diff` 和 `test-after.log` 中的证据。

## 可复现性规则

- 没有 `autopatch_commit` 的结果不得汇报。
- 不同代码 commit 的结果不能混在同一张聚合表里，除非表格明确区分 commit。
- Run 中途不得修改 verdict 定义。
- Agent 运行后不得手动编辑 `patch.diff`。
- 不得只汇报 all-case resolved rate 而隐藏 infra/invalid case。
- 即使 case 很早失败，也要保留原始产物。

## 发布规则

对外发布的评测报告必须包含：

1. 本协议的链接或路径。
2. 数据集名称和筛选标准。
3. 精确模型名称和 agent mode。
4. infra/invalid case 数量。
5. 主结果表。
6. 如比较不同模式，提供消融表。
7. 失败分类表。
8. 至少两个成功 case study 和两个失败 case study。
9. 局限性说明。

## 初始执行清单

- [ ] 创建新的 `run_id`。
- [ ] 确认工作树状态，并记录 `autopatch_commit`。
- [ ] 先选择小型 sanity dataset，再运行更大的 benchmark。
- [ ] 调用 agent 前执行 baseline validation。
- [ ] 为每个 case 保存所有必需产物。
- [ ] 按本协议规则生成 `verdict.json`。
- [ ] 发布前复查所有 `infra_error` 和 `invalid_case`。
- [ ] 同时汇报 all-case 和 valid-case resolve rate。
