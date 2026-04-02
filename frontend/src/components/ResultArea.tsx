import { useState } from 'react'
import { CheckCircle2, Copy, Check, GitPullRequest, FileCode2, Plus, Minus, Clock, Layers } from 'lucide-react'
import { cn } from '../lib/utils'
import { countDiffLines, formatElapsed } from '../lib/utils'
import type { TaskResult } from '../types'

interface Props {
  result:  TaskResult
  repoUrl: string
  issue:   string
}

export default function ResultArea({ result, repoUrl, issue }: Props) {
  const [copied, setCopied] = useState(false)
  const { added, removed }  = countDiffLines(result.diffContent)
  const isPassed            = result.reviewResult.trim().toUpperCase().startsWith('PASS')

  async function copyDiff() {
    await navigator.clipboard.writeText(result.diffContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="animate-slide-up space-y-4">
      {/* 结果摘要卡片 */}
      <div className="card-gradient-border p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          {/* 评审结论 */}
          <div className="flex items-center gap-3">
            <div className={cn(
              'flex h-10 w-10 items-center justify-center rounded-full',
              isPassed
                ? 'bg-accent-green/15 text-accent-green shadow-glow-green'
                : 'bg-accent-red/15 text-accent-red',
            )}>
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-text-primary">
                {isPassed ? 'Patch Generated Successfully' : 'Review Failed'}
              </p>
              <p className="text-xs text-text-secondary mt-0.5 max-w-md">
                {result.reviewResult.split('\n')[0]}
              </p>
            </div>
          </div>

          {/* 统计数据 */}
          <div className="flex flex-wrap gap-3">
            <Stat icon={<Plus className="h-3 w-3" />}  label="Added"   value={`+${added}`}   color="text-accent-green" />
            <Stat icon={<Minus className="h-3 w-3" />} label="Removed" value={`-${removed}`} color="text-accent-red" />
            <Stat icon={<Layers className="h-3 w-3" />} label="Steps"  value={result.stepCount} />
            <Stat icon={<Clock className="h-3 w-3" />}  label="Time"   value={formatElapsed(result.elapsedMs)} />
          </div>
        </div>

        {/* 变更文件列表 */}
        {result.changedFiles.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-bg-border pt-4">
            <span className="text-xs text-text-muted mr-1">Changed:</span>
            {result.changedFiles.map(f => (
              <span key={f} className="flex items-center gap-1 rounded border border-bg-border bg-bg-surface px-2 py-0.5 text-[11px] font-mono text-text-secondary">
                <FileCode2 className="h-3 w-3 text-brand" />
                {f}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Diff 代码块 */}
      <div className="overflow-hidden rounded-xl border border-bg-border shadow-card">
        {/* Diff 工具栏 */}
        <div className="flex items-center justify-between border-b border-bg-border bg-bg-card px-4 py-2.5">
          <div className="flex items-center gap-2 text-xs text-text-secondary font-mono">
            <FileCode2 className="h-3.5 w-3.5 text-brand" />
            <span>issue-{issue}.diff</span>
            <span className="text-text-muted">·</span>
            <span className="text-accent-green">+{added}</span>
            <span className="text-text-muted">/</span>
            <span className="text-accent-red">-{removed}</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Create PR 按钮 */}
            <a
              href={`https://github.com/${repoUrl}/issues/${issue}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-bg-border bg-bg-surface px-3 py-1.5 text-xs text-text-secondary transition-all hover:border-brand/30 hover:text-text-primary"
            >
              <GitPullRequest className="h-3.5 w-3.5" />
              View Issue
            </a>
            {/* Copy 按钮 */}
            <button
              onClick={copyDiff}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all',
                copied
                  ? 'bg-accent-green/20 text-accent-green border border-accent-green/30'
                  : 'border border-bg-border bg-bg-surface text-text-secondary hover:border-brand/30 hover:text-text-primary',
              )}
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Copied!' : 'Copy Diff'}
            </button>
          </div>
        </div>

        {/* Diff 内容（带语法高亮） */}
        <div className="overflow-x-auto">
          <DiffView diff={result.diffContent} />
        </div>
      </div>

      {/* 应用命令提示 */}
      <div className="flex items-center gap-3 rounded-lg border border-bg-border bg-bg-surface px-4 py-3">
        <span className="text-xs text-text-muted">Apply patch:</span>
        <code className="flex-1 font-mono text-xs text-accent-blue">
          git apply issue-{issue}.diff
        </code>
      </div>
    </section>
  )
}

function Stat({
  icon, label, value, color = 'text-text-primary',
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  color?: string
}) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-bg-border bg-bg-surface px-3 py-1.5">
      <span className="text-text-muted">{icon}</span>
      <span className="text-xs text-text-muted">{label}</span>
      <span className={cn('text-xs font-semibold font-mono', color)}>{value}</span>
    </div>
  )
}

// ── Diff 渲染：逐行着色 ────────────────────────────────────
function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n')

  return (
    <div className="text-xs font-mono leading-relaxed" style={{ backgroundColor: 'var(--terminal-bg)' }}>
      {lines.map((line, idx) => {
        let bg = ''
        let color = 'text-text-secondary'

        if (line.startsWith('+++) ') || line.startsWith('--- ')) {
          color = 'text-text-muted'
        } else if (line.startsWith('+')) {
          bg = 'bg-accent-green/8'
          color = 'text-accent-green'
        } else if (line.startsWith('-')) {
          bg = 'bg-accent-red/8'
          color = 'text-accent-red'
        } else if (line.startsWith('@@')) {
          bg = 'bg-accent-blue/8'
          color = 'text-accent-blue'
        } else if (line.startsWith('#')) {
          color = 'text-text-muted'
        } else if (line.startsWith('diff ') || line.startsWith('index ')) {
          color = 'text-brand-glow'
        }

        return (
          <div
            key={idx}
            className={cn('flex px-4 py-0.5 transition-colors', bg)}
          >
            <span className="mr-4 w-8 shrink-0 select-none text-right text-text-muted opacity-40">
              {idx + 1}
            </span>
            <span className={color}>{line || ' '}</span>
          </div>
        )
      })}
    </div>
  )
}
