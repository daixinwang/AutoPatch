# AutoPatch Next 源码导学

## 先理解问题

上游已有 Planner → Coder → TestRunner → Reviewer，但失败默认继续改代码。
本分支把“测错了、依赖缺失、计划错了、实现错了”区分开，并限制每条恢复路径。

## 阅读顺序

1. `agent/models.py`：为什么自然语言解释与机器路由字段要分离。
2. `core/project_profile.py`、`core/test_pipeline.py`：哪些决策可以确定性完成。
3. `core/execution/`：命令白名单不等于安全沙箱；测试本身仍是任意代码。
4. `agent/failure.py`：失败类型如何映射动作，消融如何关闭重规划。
5. `agent/next_nodes.py`：分类证据、旧计划、新计划和计数器如何传递。
6. `agent/graph.py`：条件边、工具循环、恢复路径和 checkpoint 状态。
7. `core/verification.py`、`server.py`：最终机器证据如何约束 PR。
8. `eval/scripted_recovery.py`：受控故障注入与真实模型评测的区别。

## 三个固定演示

- 正常实现：使用 recovery fixture，模型或开发者将 `service.add` 修成 `a + b`。
- 实现重试：`v3-03-implementation-error` 首轮误用绝对值，负数测试失败，再修复。
- 错误计划：`v3-02-wrong-plan` 首轮停留在 API 层，分类后修订为 service 计划。

执行命令及结果见 architecture-next.md 和 next-validation.md。脚本演示中
的计划和分类是固定输入，不能声称模型自主发现了错误。

## 面试时需要能解释

- 为什么空测试报告、无法运行测试或文本 PASS 都不能视为成功？
- 为什么失败动作不能直接信任 LLM 的 recommended_action？
- 工具步数上限触发后，如何避免消息中出现未匹配的 tool_calls？
- 为什么 Docker 日志也需要限制，而不仅是容器内存？
- 为什么消融结果只有在相同数据、配置、模型下才有可比性？
- 哪些是原项目继承，哪些代码和验证证据由本分支新增？
