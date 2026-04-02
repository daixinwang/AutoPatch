import { useState, useCallback, useRef } from 'react'
import type { AgentNode, LogEntry, TaskStatus, TaskResult, PatchInput } from '../types'
import { timestamp, extractChangedFiles } from '../lib/utils'

// ── 后端 API 地址（开发时由 Vite 代理转发）─────────────────
const API_BASE = '/api'

// ── 初始节点配置 ──────────────────────────────────────────
const INITIAL_NODES: AgentNode[] = [
  { id: 'planner',    label: 'Planner',    emoji: '📋', status: 'idle' },
  { id: 'coder',      label: 'Coder',      emoji: '💻', status: 'idle' },
  { id: 'testrunner', label: 'TestRunner', emoji: '🧪', status: 'idle' },
  { id: 'reviewer',   label: 'Reviewer',   emoji: '🔍', status: 'idle' },
]

let logIdCounter = 0
function makeLog(level: LogEntry['level'], message: string, node?: string): LogEntry {
  return { id: ++logIdCounter, timestamp: timestamp(), level, node, message }
}

// ── SSE 事件类型定义 ──────────────────────────────────────
interface SseLogEvent {
  type:     'log'
  level:    LogEntry['level']
  node?:    string
  message:  string
}
interface SseNodeEvent {
  type:    'node'
  node:    string
  status:  AgentNode['status']
  detail?: string
}
interface SseResultEvent {
  type:          'result'
  diff:          string
  reviewResult:  string
  stepCount:     number
  changedFiles:  string[]
}
interface SseErrorEvent {
  type:    'error'
  message: string
}
interface SseDoneEvent {
  type: 'done'
}
type SseEvent = SseLogEvent | SseNodeEvent | SseResultEvent | SseErrorEvent | SseDoneEvent

// ── Hook ──────────────────────────────────────────────────
export function usePatchTask() {
  const [status, setStatus] = useState<TaskStatus>('idle')
  const [nodes,  setNodes]  = useState<AgentNode[]>(INITIAL_NODES)
  const [logs,   setLogs]   = useState<LogEntry[]>([])
  const [result, setResult] = useState<TaskResult | null>(null)
  // 用 AbortController 中断进行中的 fetch 流
  const abortCtrlRef = useRef<AbortController | null>(null)

  const addLog = useCallback((level: LogEntry['level'], message: string, node?: string) => {
    setLogs(prev => [...prev, makeLog(level, message, node)])
  }, [])

  const setNodeStatus = useCallback((id: string, s: AgentNode['status'], detail?: string) => {
    setNodes(prev => prev.map(n => n.id === id ? { ...n, status: s, detail } : n))
  }, [])

  const reset = useCallback(() => {
    abortCtrlRef.current?.abort()
    abortCtrlRef.current = null
    setStatus('idle')
    setNodes(INITIAL_NODES)
    setLogs([])
    setResult(null)
  }, [])

  const startTask = useCallback(async (input: PatchInput) => {
    // 中断上一次未完成的请求
    abortCtrlRef.current?.abort()
    const ctrl = new AbortController()
    abortCtrlRef.current = ctrl

    setStatus('running')
    setNodes(INITIAL_NODES)
    setLogs([])
    setResult(null)
    const startMs = Date.now()

    addLog('system', 'AutoPatch 流水线启动')
    addLog('info', `目标仓库: ${input.repoUrl}  Issue: #${input.issueNumber}`)

    try {
      // ── 发起 POST 请求，读取 SSE 流 ──────────────────────
      const response = await fetch(`${API_BASE}/patch`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ repoUrl: input.repoUrl, issueNumber: Number(input.issueNumber) }),
        signal:  ctrl.signal,
      })

      if (!response.ok) {
        const text = await response.text()
        throw new Error(`服务器错误 ${response.status}: ${text}`)
      }

      if (!response.body) throw new Error('服务器未返回响应体')

      // ── 逐行解析 SSE 流 ─────────────────────────────────
      const reader  = response.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''
      let   finalResult: TaskResult | null = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // SSE 格式：每条事件以 \n\n 结束，data: 开头
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''   // 最后一行可能不完整，保留到下次

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue

          const jsonStr = trimmed.slice(5).trim()
          if (!jsonStr) continue

          let event: SseEvent
          try {
            event = JSON.parse(jsonStr) as SseEvent
          } catch {
            continue
          }

          // ── 按事件类型处理 ────────────────────────────
          switch (event.type) {
            case 'log':
              addLog(event.level, event.message, event.node ?? undefined)
              break

            case 'node':
              setNodeStatus(event.node, event.status, event.detail)
              break

            case 'result': {
              const elapsed = Date.now() - startMs
              finalResult = {
                diffContent:  event.diff,
                reviewResult: event.reviewResult,
                stepCount:    event.stepCount,
                elapsedMs:    elapsed,
                changedFiles: event.changedFiles.length > 0
                  ? event.changedFiles
                  : extractChangedFiles(event.diff),
              }
              break
            }

            case 'error':
              addLog('error', event.message)
              setStatus('failed')
              return

            case 'done':
              // 流结束
              break
          }
        }
      }

      // ── 流读取完毕，设置最终状态 ─────────────────────────
      if (finalResult) {
        setResult(finalResult)
        const isPassed = finalResult.reviewResult.trim().toUpperCase().startsWith('PASS')
        setStatus(isPassed ? 'success' : 'failed')
      } else {
        // 没有收到 result 事件（可能 Agent 流程中断）
        setStatus('failed')
        addLog('warn', '流水线结束但未收到结果，请检查后端日志')
      }

    } catch (err) {
      if ((err as Error).name === 'AbortError') return   // 用户主动中断，不报错

      const msg = err instanceof Error ? err.message : String(err)

      // ── 后端未启动时的友好提示 ───────────────────────────
      if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
        addLog('error', '无法连接到后端服务（http://localhost:8000）')
        addLog('warn',  '请先启动后端：source .venv/bin/activate && uvicorn server:app --reload --port 8000')
        addLog('warn',  '后端未运行时，可在 usePatchTask.ts 中切换回 Mock 模式进行 UI 调试')
      } else {
        addLog('error', `流水线异常: ${msg}`)
      }
      setStatus('failed')
    }
  }, [addLog, setNodeStatus])

  return { status, nodes, logs, result, startTask, reset }
}
