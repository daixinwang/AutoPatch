import { useEffect, useRef } from 'react'
import { cn } from '../lib/utils'
import { useT } from '../contexts/LanguageContext'
import type { LogEntry, LogLevel } from '../types'

interface Props {
  logs: LogEntry[]
}

// 日志级别 → Tailwind 颜色 class（accent 颜色在深浅模式下都清晰可读）
const levelStyle: Record<LogLevel, { color: string; prefix: string }> = {
  system:  { color: 'text-text-muted',    prefix: '  ·  ' },
  info:    { color: 'text-accent-blue',   prefix: ' INF ' },
  tool:    { color: 'text-accent-purple', prefix: ' RUN ' },
  warn:    { color: 'text-accent-yellow', prefix: ' WRN ' },
  success: { color: 'text-accent-green',  prefix: ' OK  ' },
  error:   { color: 'text-accent-red',    prefix: ' ERR ' },
}

const nodeColors: Record<string, string> = {
  Planner:    'text-accent-blue',
  Coder:      'text-accent-purple',
  TestRunner: 'text-accent-yellow',
  Reviewer:   'text-accent-green',
}

function LogLine({ entry }: { entry: LogEntry }) {
  const style = levelStyle[entry.level]
  return (
    <div className="flex items-start gap-2 text-[12px] leading-relaxed font-mono animate-fade-in">
      {/* 时间戳 */}
      <span className="shrink-0 text-text-muted opacity-60">{entry.timestamp}</span>
      {/* 级别标签 */}
      <span className={cn('shrink-0 text-[10px] font-semibold tracking-widest', style.color)}>
        {style.prefix}
      </span>
      {/* 节点来源 */}
      {entry.node && (
        <span className={cn('shrink-0 text-[10px] font-medium', nodeColors[entry.node] ?? 'text-text-muted')}>
          [{entry.node}]
        </span>
      )}
      {/* 消息正文：用 CSS 变量保证在两种主题下都清晰 */}
      <span className="break-all" style={{ color: 'var(--terminal-text)' }}>
        {entry.message}
        {entry.streaming && (
          <span
            className="inline-block ml-0.5 h-3 w-1.5 align-middle animate-[typing_0.7s_steps(2)_infinite]"
            style={{ backgroundColor: 'var(--terminal-cursor)' }}
          />
        )}
      </span>
    </div>
  )
}

export default function TerminalWindow({ logs }: Props) {
  const t = useT()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <section className="animate-slide-up">
      {/* 外层容器：背景、边框全部跟随主题变量 */}
      <div
        className="overflow-hidden rounded-xl shadow-card transition-colors"
        style={{
          backgroundColor: 'var(--terminal-bg)',
          border: '1px solid var(--terminal-border)',
        }}
      >
        {/* macOS 标题栏 */}
        <div
          className="flex items-center gap-2 px-4 py-3 transition-colors"
          style={{
            backgroundColor: 'var(--terminal-title)',
            borderBottom: '1px solid var(--terminal-border)',
          }}
        >
          <span className="h-3 w-3 rounded-full bg-[#ff5f57] shadow-[0_0_4px_#ff5f5780]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e] shadow-[0_0_4px_#febc2e80]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840] shadow-[0_0_4px_#28c84080]" />
          <span className="mx-auto text-xs font-mono" style={{ color: 'var(--terminal-text-dim)' }}>
            {t.terminal.shellTitle}
          </span>
          {logs.length > 0 && (
            <span className="text-[10px] font-mono" style={{ color: 'var(--terminal-text-dim)' }}>
              {logs.length} {t.terminal.linesUnit}
            </span>
          )}
        </div>

        {/* 日志内容区 */}
        <div className="h-72 overflow-y-auto px-4 py-3 space-y-1">
          {logs.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <div className="flex items-center gap-2 text-xs font-mono" style={{ color: 'var(--terminal-text-dim)' }}>
                <span className="h-2 w-2 rounded-full bg-accent-green animate-pulse" />
                {t.terminal.waiting}
              </div>
            </div>
          ) : (
            <>
              {/* Prompt 行 */}
              <div className="mb-2 text-[12px] font-mono">
                <span style={{ color: 'var(--terminal-prompt)' }}>autopatch</span>
                <span style={{ color: 'var(--terminal-text-dim)' }}> ~ </span>
                <span style={{ color: 'var(--terminal-text)' }}>python autopatch.py</span>
                <span
                  className="ml-1 inline-block h-3.5 w-1.5 animate-[typing_1s_steps(2)_infinite] align-middle"
                  style={{ backgroundColor: 'var(--terminal-cursor)' }}
                />
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
