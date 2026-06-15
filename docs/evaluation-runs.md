# 评测运行记录

本文档记录 AutoPatch 的真实评测运行结果。它只记录可复现配置摘要、指标和观察结论，不记录 API Key、完整 workspace 路径或大段模型输出。

## 2026-06-15 sanity-v1 / 小米 Mimo + 阿里百炼 Embedding

### 运行配置

| 项目 | 值 |
|---|---|
| 数据集 | `sanity-v1` |
| Run ID | `sanity-v1-agent-full-mimo-v25-dashscope` |
| Planner | `mimo-v2.5` |
| Coder | `mimo-v2.5-pro` |
| TestRunner | `mimo-v2.5` |
| Reviewer | `mimo-v2.5-pro` |
| Embedding endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Embedding model | `text-embedding-v4` |
| Embedding dimensions | `1024` |
| LangSmith tracing | `false` |

### 结果摘要

| 指标 | 数量 |
|---|---:|
| Total cases | 5 |
| Resolved | 4 |
| Partial | 0 |
| Failed | 0 |
| Invalid case | 1 |
| Infra error | 0 |

### Case 结果

| Case | Verdict | 说明 |
|---|---|---|
| `invalid-baseline` | `invalid_case` | `FAIL_TO_PASS` 在修复前已通过，正确识别为无效样本 |
| `py-multi-file` | `resolved` | 跨文件定价逻辑修复成功 |
| `py-regression-risk` | `resolved` | 修复目标行为，同时保留回归保护测试 |
| `py-single-file` | `resolved` | 单文件折扣计算修复成功 |
| `py-test-modification-guard` | `resolved` | 未修改测试文件，业务文件修复成功 |

### 观察

- 真实模型链路已经可跑通：RAG 建索引、Planner、Coder、TestRunner、Reviewer 和 sanity runner 均能完成闭环。
- `invalid-baseline` 被排除为 `invalid_case`，说明基线校验能阻止无效样本污染成功率。
- 所有有效 case 的最终 diff 都只修改业务文件，没有修改测试文件。
- 运行中多次出现 `run_python_script` 被传入 `/dev/stdin` 或 `/tmp/list_files.py` 的情况。路径安全策略正确拦截了这些调用，最终模型能恢复，但这暴露出工具提示不够明确。

### 后续行动

- 已将 `run_python_script` 的工具说明和错误提示改为明确要求使用 workspace 内相对路径。
- 对临时脚本约定为 `.autopatch_tmp/<name>.py`，模型需要先用 `write_and_replace_file` 创建脚本，再调用 `run_python_script`。
- 下一批评测应进入 `sanity-v2`，覆盖更接近真实 Issue 的多文件调用链、文档约定、错误消息定位、过拟合风险和预期困难样本。

## 2026-06-15 sanity-v2 / 小米 Mimo + 阿里百炼 Embedding

### 运行配置

| 项目 | 值 |
|---|---|
| 数据集 | `sanity-v2` |
| Run ID | `sanity-v2-agent-mimo-v25-dashscope` |
| Planner | `mimo-v2.5` |
| Coder | `mimo-v2.5-pro` |
| TestRunner | `mimo-v2.5` |
| Reviewer | `mimo-v2.5-pro` |
| Embedding endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Embedding model | `text-embedding-v4` |
| Embedding dimensions | `1024` |
| LangSmith tracing | `false` |

### 结果摘要

| 指标 | 数量 |
|---|---:|
| Total cases | 5 |
| Resolved | 5 |
| Partial | 0 |
| Failed | 0 |
| Invalid case | 0 |
| Infra error | 0 |

### Case 结果

| Case | Verdict | 修改文件 | Agent steps |
|---|---|---|---:|
| `py-call-chain-normalization` | `resolved` | `accounts/service.py` | 15 |
| `py-error-message-indirect` | `resolved` | `orders/validators.py` | 20 |
| `py-readme-contract` | `resolved` | `billing/money.py` | 15 |
| `py-security-boundary` | `resolved` | `security/urls.py` | 19 |
| `py-stateful-edge-case` | `resolved` | `warehouse/inventory.py` | 15 |

### 观察

- `sanity-v2` 的 5 个有效样本全部修复成功，且没有 case 修改测试文件。
- 相比 `sanity-v1`，这批样本覆盖了间接错误消息定位、README 业务约定、跨 3 个文件调用链、安全边界和状态边界。
- `py-error-message-indirect` 与 `py-security-boundary` 运行中观察到 TestRunner 误试 `go` / `cargo` 命令，工具返回 `FileNotFoundError` 后模型最终恢复并完成。这说明上一轮 `run_python_script` 路径问题已改善，但 TestRunner 的项目类型选择仍可收紧。
- 所有最终 diff 都落在预期业务文件上，说明当前小型本地 benchmark 对“测试文件修改”和“明显回归”已有基本约束力。

### 后续行动

- 优先优化 TestRunner 项目类型选择：当 repo 明确是 Python fixture 且存在 pytest selector 时，避免探索 `go`、`cargo` 等无关命令。
- 增加 `sanity-v2` mock patches，覆盖 `security-boundary` 的过宽字符串匹配回归、`stateful-edge-case` 的确认流程回归。
- 下一阶段应设计 `sanity-v3` 或小型真实仓库集，加入更长调用链、更大文件数量和一个预期失败样本，避免 10/10 的 sanity case 给出过度乐观信号。

## 2026-06-15 sanity-v2 unified runner / 小米 Mimo + 阿里百炼 Embedding

### 运行配置

| 项目 | 值 |
|---|---|
| 数据集 | `sanity-v2` |
| Run ID | `sanity-v2-unified-agent-mimo` |
| 评测入口 | `python -m eval.unified --dataset sanity-v2 --mode agent` |
| AutoPatch commit | `637c3b6842ab55e36ec22f3ef881436b013c4ee0` |
| Autopatch dirty | `true` |
| Planner | `mimo-v2.5` |
| Coder | `mimo-v2.5-pro` |
| TestRunner | `mimo-v2.5` |
| Reviewer | `mimo-v2.5-pro` |
| Embedding endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Embedding model | `text-embedding-v4` |
| Embedding dimensions | `1024` |
| Python | `3.9.6` |
| Docker | `false` |

### 结果摘要

| 指标 | 数量 |
|---|---:|
| Total cases | 5 |
| Resolved | 5 |
| Partial | 0 |
| Failed | 0 |
| Agent timeout | 0 |
| Invalid case | 0 |
| Infra error | 0 |
| Resolved rate all | 1.0 |
| Resolved rate valid | 1.0 |

### Case 结果

| Case | Verdict | 修改文件 |
|---|---|---|
| `py-call-chain-normalization` | `resolved` | `accounts/service.py` |
| `py-error-message-indirect` | `resolved` | `orders/validators.py` |
| `py-readme-contract` | `resolved` | `billing/money.py` |
| `py-security-boundary` | `resolved` | `security/urls.py` |
| `py-stateful-edge-case` | `resolved` | `warehouse/inventory.py` |

### 观察

- 统一 runner 下的真实 agent 链路跑通，5 个 `sanity-v2` case 全部 `resolved`。
- 每个 case 的 `FAIL_TO_PASS` 和 `PASS_TO_PASS` selector 均在 patch 后通过，且 `changed-files.json` 显示没有修改测试文件。
- 运行中仍观察到 TestRunner 偶发尝试无关命令，例如 `go` / `cargo`；工具失败后 agent 最终恢复并完成。
- `py-readme-contract` 触发过 reviewer reject / retry，最终机器验证仍判定为 `resolved`。
- 本次 run 暴露并修复了统一 CLI 的 `.env` 加载顺序问题：`eval.unified` 必须在导入 `core.config` 前加载 `.env`，否则会误用默认 Claude 模型名。

### 后续行动

- 将 `swebench-smoke` 作为下一步真实 SWE-bench Lite smoke 测试，验证统一 runner 在外部真实实例上的环境准备和报告产物。
- 继续收紧 TestRunner 的项目类型选择，Python fixture 下优先使用 pytest selector，避免探索无关语言工具。
