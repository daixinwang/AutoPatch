# sanity-v2 评测计划

`sanity-v2` 的目标是从“链路可跑”推进到“更接近真实 Issue”。它仍然是本地小型 benchmark，但 case 设计要覆盖更复杂的定位、约束和回归风险。

## 目标

- 保持运行成本低：每个 case 都是小型 Python 项目，默认用 `pytest` selector 验证。
- 保持可解释：每个 case 都有明确的 `FAIL_TO_PASS` 和 `PASS_TO_PASS`。
- 增加真实感：问题描述不总是直接点名 bug 所在函数，需要读调用链、错误信息或 README 约定。
- 保留安全边界：Agent 不应修改测试文件，评测仍通过 `changed-files.json` 检查。

## Case 清单

| Case | 目的 | 修复前状态 | 期望能力 |
|---|---|---|---|
| `py-error-message-indirect` | 错误消息间接定位 | F2P 检查异常消息失败，P2P 检查合法输入通过 | 根据 API 层测试定位到底层 validator |
| `py-readme-contract` | README 约定驱动修复 | F2P 检查 README 中的四舍五入规则失败，P2P 检查普通格式化通过 | 读取项目文档并按业务约定修改 |
| `py-call-chain-normalization` | 跨 3 个文件调用链 | F2P 检查用户查找前应规范化邮箱失败，P2P 检查未知用户仍返回 `None` | 从服务入口追到 repository key 约定 |
| `py-security-boundary` | 防止字符串过拟合 | F2P 检查伪造 internal host 失败，P2P 检查合法子域仍通过 | 正确解析 hostname，而不是简单字符串包含 |
| `py-stateful-edge-case` | 状态边界和回归保护 | F2P 检查 cancel 后释放库存失败，P2P 检查 confirm 后扣库存通过 | 理解对象状态转换，避免破坏已有流程 |

## 运行命令

Baseline-only：

```bash
python -m eval.sanity \
  --baseline-only \
  --cases-dir eval/cases/sanity-v2 \
  --results-dir eval/results \
  --run-id sanity-v2-baseline
```

真实 Agent：

```bash
python -m eval.sanity \
  --agent \
  --cases-dir eval/cases/sanity-v2 \
  --results-dir eval/results \
  --run-id sanity-v2-agent-mimo-v25-dashscope
```

## 通过标准

- baseline-only：5 个 case 都应是 `baseline_ready`。
- 真实 Agent 第一轮目标：至少 3/5 `resolved`，且无 `infra_error`。
- 如果出现 `failed`，优先看：
  - 是否定位错文件；
  - 是否忽略 README/错误消息；
  - 是否改了测试；
  - 是否因工具使用不稳定造成非业务失败。
