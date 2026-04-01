import { useState, useCallback, useRef } from 'react'
import type { AgentNode, LogEntry, TaskStatus, TaskResult, PatchInput } from '../types'
import { timestamp, extractChangedFiles } from '../lib/utils'

// ── 初始节点配置 ──────────────────────────────────────────
const INITIAL_NODES: AgentNode[] = [
  { id: 'planner',     label: 'Planner',     emoji: '📋', status: 'idle' },
  { id: 'coder',       label: 'Coder',       emoji: '💻', status: 'idle' },
  { id: 'testrunner',  label: 'TestRunner',  emoji: '🧪', status: 'idle' },
  { id: 'reviewer',    label: 'Reviewer',    emoji: '🔍', status: 'idle' },
]

let logIdCounter = 0
function makeLog(
  level: LogEntry['level'],
  message: string,
  node?: string,
): LogEntry {
  return {
    id:        ++logIdCounter,
    timestamp: timestamp(),
    level,
    node,
    message,
  }
}

// ── Mock 流水线模拟（后续替换为真实 SSE/WebSocket）──────────
async function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms))
}

// ── Hook ──────────────────────────────────────────────────
export function usePatchTask() {
  const [status,  setStatus]  = useState<TaskStatus>('idle')
  const [nodes,   setNodes]   = useState<AgentNode[]>(INITIAL_NODES)
  const [logs,    setLogs]    = useState<LogEntry[]>([])
  const [result,  setResult]  = useState<TaskResult | null>(null)
  const abortRef = useRef(false)

  /** 追加单条日志 */
  const addLog = useCallback((
    level: LogEntry['level'],
    message: string,
    node?: string,
  ) => {
    setLogs(prev => [...prev, makeLog(level, message, node)])
  }, [])

  /** 更新单个节点状态 */
  const setNodeStatus = useCallback((
    id: string,
    status: AgentNode['status'],
    detail?: string,
  ) => {
    setNodes(prev =>
      prev.map(n => n.id === id ? { ...n, status, detail } : n)
    )
  }, [])

  /** 重置所有状态 */
  const reset = useCallback(() => {
    abortRef.current = true
    setStatus('idle')
    setNodes(INITIAL_NODES)
    setLogs([])
    setResult(null)
  }, [])

  /** 启动任务（Mock 模式演示，真实接入时替换 simulatePipeline） */
  const startTask = useCallback(async (input: PatchInput) => {
    abortRef.current = false
    setStatus('running')
    setNodes(INITIAL_NODES)
    setLogs([])
    setResult(null)
    const startMs = Date.now()

    addLog('system', `AutoPatch 流水线启动`)
    addLog('info',   `目标仓库: ${input.repoUrl}  Issue: #${input.issueNumber}`)
    await sleep(400)

    try {
      // ── Step 1: GitHub API 拉取 Issue ──
      addLog('info', `正在从 GitHub 拉取 Issue #${input.issueNumber}...`)
      await sleep(800)
      addLog('success', `Issue 拉取成功: "Add type annotations to calc module"`)
      await sleep(300)

      // ── Step 2: Clone 仓库 ──
      addLog('info', `正在 clone 仓库 ${input.repoUrl}...`)
      await sleep(1200)
      addLog('success', `仓库 clone 完成 → /tmp/autopatch_repo_xk82j/`)
      await sleep(200)

      // ── Node: Planner ──
      if (abortRef.current) return
      setNodeStatus('planner', 'running')
      addLog('info', '分析 Issue，制定修复计划...', 'Planner')
      await sleep(1500)
      addLog('success', '执行计划已生成：1) 检索 calc.py  2) 添加类型注解  3) 补充 docstring', 'Planner')
      setNodeStatus('planner', 'done')
      await sleep(300)

      // ── Node: Coder ──
      if (abortRef.current) return
      setNodeStatus('coder', 'running')
      addLog('info', 'Coder 开始检索代码库...', 'Coder')
      await sleep(600)
      addLog('tool', '调用工具: list_directory(".")', 'Coder')
      await sleep(500)
      addLog('tool', '调用工具: find_definition("add")', 'Coder')
      await sleep(700)
      addLog('tool', '调用工具: read_file("calc.py")', 'Coder')
      await sleep(800)
      addLog('info', '分析现有代码，生成修复补丁...', 'Coder')
      await sleep(1200)
      addLog('tool', '调用工具: write_and_replace_file("calc.py", <新内容>)', 'Coder')
      await sleep(600)
      addLog('success', '文件写入完成', 'Coder')
      setNodeStatus('coder', 'done')
      await sleep(300)

      // ── Node: TestRunner ──
      if (abortRef.current) return
      setNodeStatus('testrunner', 'running')
      addLog('info', 'TestRunner 开始执行测试...', 'TestRunner')
      await sleep(600)
      addLog('tool', '调用工具: run_python_script("calc.py")', 'TestRunner')
      await sleep(1000)
      addLog('success', '✅ 脚本运行通过 (exit 0)', 'TestRunner')
      await sleep(300)
      addLog('tool', '调用工具: run_pytest(".", "-v --tb=short")', 'TestRunner')
      await sleep(1500)
      addLog('success', '✅ 4 passed in 0.12s', 'TestRunner')
      setNodeStatus('testrunner', 'done')
      await sleep(300)

      // ── Node: Reviewer ──
      if (abortRef.current) return
      setNodeStatus('reviewer', 'running')
      addLog('info', '开始代码评审...', 'Reviewer')
      await sleep(600)
      addLog('tool', '调用工具: read_file("calc.py")', 'Reviewer')
      await sleep(900)
      addLog('info', '检查类型注解、docstring、边界情况...', 'Reviewer')
      await sleep(1000)
      addLog('success', '✅ PASS — 所有函数均有类型注解和 docstring，divide 正确处理除以零', 'Reviewer')
      setNodeStatus('reviewer', 'done')
      await sleep(400)

      // ── 生成 Diff ──
      if (abortRef.current) return
      addLog('info', '正在生成 diff 补丁文件...')
      await sleep(600)

      const mockDiff = generateMockDiff(input.repoUrl, input.issueNumber)
      addLog('success', `Diff 生成完成 → issue-${input.issueNumber}.diff`)

      const elapsed = Date.now() - startMs
      setResult({
        diffContent:  mockDiff,
        reviewResult: 'PASS\n理由：所有函数均已实现，类型注解完整，docstring 清晰，divide 正确抛出 ValueError。',
        stepCount:    12,
        elapsedMs:    elapsed,
        changedFiles: extractChangedFiles(mockDiff),
      })

      setStatus('success')
      addLog('system', `🎉 流水线完成！耗时 ${(elapsed / 1000).toFixed(1)}s`)

    } catch (err) {
      if (abortRef.current) return
      addLog('error', `流水线异常: ${err instanceof Error ? err.message : String(err)}`)
      setStatus('failed')
    }
  }, [addLog, setNodeStatus])

  return { status, nodes, logs, result, startTask, reset }
}

// ── Mock Diff 生成 ────────────────────────────────────────
function generateMockDiff(repo: string, issue: string): string {
  return `# AutoPatch Generated Diff
# Repository   : https://github.com/${repo}
# Issue        : #${issue}
# Review Result: PASS
# Apply with   : git apply issue-${issue}.diff

diff --git a/calc.py b/calc.py
index a1b2c3d..e4f5g6h 100644
--- a/calc.py
+++ b/calc.py
@@ -1,8 +1,36 @@
-def add(a, b):
-    return a + b
-
-def subtract(a, b):
-    return a - b
-
-def multiply(a, b):
-    return a * b
-
-def divide(a, b):
-    return a / b
+"""
+calc.py
+-------
+基础数学工具模块。
+"""
+from typing import Union
+
+Number = Union[int, float]
+
+
+def add(a: Number, b: Number) -> Number:
+    """计算两个数的和。
+
+    Args:
+        a: 第一个操作数
+        b: 第二个操作数
+
+    Returns:
+        a 与 b 的和
+    """
+    return a + b
+
+
+def subtract(a: Number, b: Number) -> Number:
+    """计算两个数的差（a - b）。"""
+    return a - b
+
+
+def multiply(a: Number, b: Number) -> Number:
+    """计算两个数的积。"""
+    return a * b
+
+
+def divide(a: Number, b: Number) -> Number:
+    """计算两个数的商（a / b）。
+
+    Raises:
+        ValueError: 当 b 为 0 时抛出，防止除以零错误。
+    """
+    if b == 0:
+        raise ValueError("除数不能为零")
+    return a / b
`
}
