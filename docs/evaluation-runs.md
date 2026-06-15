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
