// ── Agent 节点状态 ───────────────────────────────────────
export type NodeStatus = 'idle' | 'running' | 'done' | 'error' | 'retrying'

export interface AgentNode {
  id:     string
  label:  string
  emoji:  string
  status: NodeStatus
  detail?: string   // 当前节点的附加说明（如 "第2次打回"）
}

// ── 日志条目 ────────────────────────────────────────────
export type LogLevel = 'info' | 'tool' | 'warn' | 'success' | 'error' | 'system'

export interface LogEntry {
  id:        number
  timestamp: string
  level:     LogLevel
  node?:     string   // 来源节点名称
  message:   string
}

// ── 任务状态机 ───────────────────────────────────────────
export type TaskStatus =
  | 'idle'       // 初始，等待用户输入
  | 'running'    // Agent 正在运行
  | 'success'    // 流水线完成且 Reviewer PASS
  | 'failed'     // 流水线完成但失败或出错

// ── 任务结果 ────────────────────────────────────────────
export interface TaskResult {
  diffContent:   string   // unified diff 文本
  reviewResult:  string   // Reviewer 的最终结论
  stepCount:     number   // 总步骤数
  elapsedMs:     number   // 耗时毫秒
  changedFiles:  string[] // 变更文件列表
}

// ── 表单输入 ────────────────────────────────────────────
export interface PatchInput {
  repoUrl:     string   // e.g. "owner/repo" or full URL
  issueNumber: string   // e.g. "42"
}
