import { useEffect, useRef } from 'react'
import { cn } from '../lib/utils'
import type { LogEntry, LogLevel } from '../types'

interface Props {
  logs: LogEntry[]
}

// 日志级别 → 颜色 & 前缀
const levelStyle: Record<LogLevel, { color: string; prefix: string }> = {
  system:  { color: 'text-text-muted',     prefix: '  ·  ' },
  info:    { color: 'text-accent-blue',    prefix: ' INF ' },
  tool:    { color: 'text-accent-purple',  prefix: ' RUN ' },
  warn:    { color: 'text-accent-yellow',  prefix: ' WRN ' },
  success: { color: 'text-accent-green',   prefix: ' OK  ' },
  error:   { color: 'text-accent-red',     prefix: ' ERR ' },
}

// 节点名 → 颜色
const nodeColors: Record<string, string> = {
  Planner:    'text-accent-blue',
  Coder:      'text-accent-purple',
  TestRunner: 'text-accent-yellow',
  Reviewer:   'text-accent-green',
}

function LogLine({ entry }: { entry: LogEntry }) {
  const style = levelStyle[entry.level]
  return (
    <div className={cn('flex items-start gap-2 text-[12px] leading-relaxed font-mono animate-fade-in')}>
      {/* 时间戳 */}
      <span className="shrink-0 text-text-muted opacity-60">{entry.timestamp}</span>
      {/* 级别标签 */}
      <span className={cn('shrink-0 rounded text-[10px] font-semibold tracking-widest', style.color)}>
        {style.prefix}
      </span>
      {/* 节点来源 */}
      {entry.node && (
        <span className={cn(
          'shrink-0 text-[10px] font-medium',
          nodeColors[entry.node] ?? 'text-text-muted',
        )}>
          [{entry.node}]
        </span>
      )}
      {/* 消息正文 */}
      <span className="text-text-secondary break-all">{entry.message}</span>
    </div>
  )
}

export default function TerminalWindow({ logs }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // 新日志出现时自动滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <section className="animate-slide-up">
      <div className="overflow-hidden rounded-xl border border-bg-border bg-bg-base shadow-card">
        {/* macOS 标题栏 */}
        <div className="flex items-center gap-2 border-b border-bg-border bg-bg-card px-4 py-3">
          {/* 红黄绿圆点 */}
          <span className="h-3 w-3 rounded-full bg-[#ff5f57] shadow-[0_0_4px_#ff5f5780]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e] shadow-[0_0_4px_#febc2e80]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840] shadow-[0_0_4px_#28c84080]" />
          <span className="mx-auto text-xs text-text-muted font-mono">
            autopatch — bash
          </span>
          {/* 日志计数 */}
          {logs.length > 0 && (
            <span className="text-[10px] text-text-muted font-mono">
              {logs.length} lines
            </span>
          )}
        </div>

        {/* 日志内容区 */}
        <div className="h-72 overflow-y-auto px-4 py-3 space-y-1">
          {logs.length === 0 ? (
            // 空状态：等待任务
            <div className="flex h-full items-center justify-center">
              <div className="flex items-center gap-2 text-text-muted text-xs font-mono">
                <span className="h-2 w-2 rounded-full bg-accent-green animate-pulse" />
                Waiting for task input...
              </div>
            </div>
          ) : (
            <>
              {/* Prompt 行 */}
              <div className="mb-2 text-[12px] font-mono text-accent-green">
                <span className="text-brand">autopatch</span>
                <span className="text-text-muted"> ~ </span>
                <span className="text-text-primary">python autopatch.py</span>
                <span className="ml-1 inline-block h-3.5 w-1.5 animate-[typing_1s_steps(2)_infinite] bg-text-primary align-middle" />
              </div>

              {logs.map(entry => (
                <LogLine key={entry.id} entry={entry} />
              ))}
            </>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </section>
  )
}
