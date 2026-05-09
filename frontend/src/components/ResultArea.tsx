import { useState, useRef, useEffect } from 'react'
import { CheckCircle2, Copy, Check, GitPullRequest, FileCode2, Plus, Minus, Clock, Layers, ExternalLink, Loader2 } from 'lucide-react'
import { cn } from '../lib/utils'
import { countDiffLines, formatElapsed } from '../lib/utils'
import type { TaskResult } from '../types'

interface Props {
  result:  TaskResult
  repoUrl: string
  issue:   string
}

type PRStatus = 'idle' | 'creating' | 'success' | 'error'

export default function ResultArea({ result, repoUrl, issue }: Props) {
  const [copied, setCopied] = useState(false)
  const [prStatus, setPrStatus] = useState<PRStatus>('idle')
  const [prUrl,    setPrUrl]    = useState('')
  const [prError,  setPrError]  = useState('')
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => () => { abortRef.current?.abort() }, [])
  const { added, removed }  = countDiffLines(result.diffContent)
  const isPassed            = result.reviewResult.trim().toUpperCase().startsWith('PASS')

  async function copyDiff() {
    await navigator.clipboard.writeText(result.diffContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleCreatePR() {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setPrStatus('creating')
    setPrError('')
    try {
      const issueNum = parseInt(issue, 10)
      if (isNaN(issueNum) || issueNum <= 0) throw new Error('Invalid issue number')

      const res = await fetch('/api/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repoUrl:     repoUrl,
          issueNumber: issueNum,
          diffContent: result.diffContent,
        }),
        signal: controller.signal,
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(data.detail ?? 'Unknown error')
      }
      const { prUrl: url } = await res.json()
      setPrUrl(url)
      setPrStatus('success')
    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') return
      setPrError(e instanceof Error ? e.message : 'Failed to create PR')
      setPrStatus('error')
    }
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
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
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
              <span
                key={f}
                className="flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-mono transition-colors"
                style={{
                  borderColor: 'var(--bg-border)',
                  backgroundColor: 'var(--bg-surface)',
                  color: 'var(--text-secondary)',
                }}
              >
                <FileCode2 className="h-3 w-3 text-brand" />
                {f}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Diff 代码块 */}
      <div
        className="overflow-hidden rounded-xl shadow-card transition-colors"
        style={{ border: '1px solid var(--terminal-border)', backgroundColor: 'var(--terminal-bg)' }}
      >
        {/* Diff 工具栏 */}
        <div
          className="flex items-center justify-between px-4 py-2.5 transition-colors"
          style={{ backgroundColor: 'var(--terminal-title)', borderBottom: '1px solid var(--terminal-border)' }}
        >
          <div className="flex items-center gap-2 text-xs text-text-secondary font-mono">
            <FileCode2 className="h-3.5 w-3.5 text-brand" />
            <span>issue-{issue}.diff</span>
            <span className="text-text-muted">·</span>
            <span className="text-accent-green">+{added}</span>
            <span className="text-text-muted">/</span>
            <span className="text-accent-red">-{removed}</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Create PR / View PR 按钮 */}
            {prStatus === 'success' ? (
              <a
                href={prUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all"
                style={{ borderColor: '#22d3a5', backgroundColor: 'rgba(34,211,165,0.1)', color: '#22d3a5' }}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View PR
              </a>
            ) : (
              <button
                onClick={handleCreatePR}
                disabled={prStatus === 'creating'}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-all hover:border-brand/30 hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)' }}
              >
                {prStatus === 'creating'
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <GitPullRequest className="h-3.5 w-3.5" />}
                {prStatus === 'creating' ? 'Creating…' : 'Create PR'}
              </button>
            )}

            {/* Copy 按钮 */}
            <button
              onClick={copyDiff}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all',
                copied
                  ? 'bg-accent-green/20 text-accent-green border border-accent-green/30'
                  : 'border hover:border-brand/30 hover:text-text-primary',
              )}
              style={!copied ? { borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)' } : undefined}
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
      <div
        className="flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors"
        style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
      >
        <span className="text-xs text-text-muted">Apply patch:</span>
        <code className="flex-1 font-mono text-xs text-accent-blue">
          git apply issue-{issue}.diff
        </code>
      </div>

      {/* PR 创建错误提示 */}
      {prStatus === 'error' && (
        <div className="rounded-lg border px-4 py-3 text-xs text-accent-red animate-slide-up"
          style={{ borderColor: 'rgba(248,113,113,0.3)', backgroundColor: 'rgba(248,113,113,0.08)' }}
        >
          PR 创建失败：{prError}
        </div>
      )}
    </section>
  )
}

function Stat({
  icon, label, value, color,
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  color?: string
}) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 transition-colors"
      style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
    >
      <span className="text-text-muted">{icon}</span>
      <span className="text-xs text-text-muted">{label}</span>
      {/* color prop 有值时用 Tailwind class（+/-行），无值时用主题变量 */}
      <span
        className={cn('text-xs font-semibold font-mono', color)}
        style={!color ? { color: 'var(--text-primary)' } : undefined}
      >
        {value}
      </span>
    </div>
  )
}

// ── Diff 渲染：完全跟随主题的逐行着色 ──────────────────────
function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n')

  return (
    // 背景跟随主题变量（深色:#0d1117 / 浅色:#f8fafc）
    <div
      className="text-xs font-mono leading-relaxed transition-colors"
      style={{ backgroundColor: 'var(--terminal-bg)' }}
    >
      {lines.map((line, idx) => {
        // 用 inline style 设置行背景，确保跟随 CSS 变量
        let rowStyle: React.CSSProperties = {}
        let color = 'var(--terminal-text)'

        if (line.startsWith('+++') || line.startsWith('---')) {
          color = 'var(--terminal-text-dim)'
        } else if (line.startsWith('+')) {
          rowStyle = { backgroundColor: 'var(--diff-add-bg)',    borderLeft: '2px solid #22d3a5' }
          color = '#16a34a'   // green-600，深浅模式都清晰
        } else if (line.startsWith('-')) {
          rowStyle = { backgroundColor: 'var(--diff-remove-bg)', borderLeft: '2px solid #f87171' }
          color = '#dc2626'   // red-600
        } else if (line.startsWith('@@')) {
          rowStyle = { backgroundColor: 'var(--diff-hunk-bg)' }
          color = '#2563eb'   // blue-600
        } else if (line.startsWith('#')) {
          color = 'var(--terminal-text-dim)'
        } else if (line.startsWith('diff ') || line.startsWith('index ')) {
          color = '#10a37f'   // brand green
        }

        return (
          <div key={idx} className="flex px-4 py-0.5 transition-colors" style={rowStyle}>
            <span
              className="mr-4 w-8 shrink-0 select-none text-right opacity-40"
              style={{ color: 'var(--terminal-text-dim)' }}
            >
              {idx + 1}
            </span>
            <span style={{ color }}>{line || ' '}</span>
          </div>
        )
      })}
    </div>
  )
}
