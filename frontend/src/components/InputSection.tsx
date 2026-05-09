import { useState } from 'react'
import { GitBranch, Hash, Rocket, Loader2, RotateCcw, Eye } from 'lucide-react'
import { cn } from '../lib/utils'
import { useT } from '../contexts/LanguageContext'
import type { PatchInput, TaskStatus } from '../types'
import type { PreviewStatus } from '../hooks/useIssuePreview'

interface Props {
  status:        TaskStatus
  onSubmit:      (input: PatchInput) => void
  onReset:       () => void
  onPreview:     (input: PatchInput) => void
  previewStatus: PreviewStatus
}

export default function InputSection({ status, onSubmit, onReset, onPreview, previewStatus }: Props) {
  const t = useT()
  const [repo,  setRepo]  = useState('daixinwang/AutoPatch')
  const [issue, setIssue] = useState('42')

  const isRunning = status === 'running'
  const isDone    = status === 'success' || status === 'failed'

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!repo.trim() || !issue.trim()) return
    onSubmit({ repoUrl: repo.trim(), issueNumber: issue.trim() })
  }

  return (
    <section className="animate-slide-up">
      <div className="card-gradient-border p-6">
        <div className="mb-5 flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
          <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wider">
            {t.input.sectionTitle}
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Repo URL */}
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary">
                <GitBranch className="h-3.5 w-3.5" />
                {t.input.repoLabel}
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-text-muted select-none">
                  {t.input.repoPrefix}
                </span>
                <input
                  type="text"
                  value={repo}
                  onChange={e => setRepo(e.target.value)}
                  placeholder={t.input.repoPlaceholder}
                  disabled={isRunning}
                  className={cn(
                    'w-full rounded-lg border pl-[88px] pr-4 py-2.5 text-sm',
                    'placeholder:text-text-muted font-mono',
                    'outline-none transition-all',
                    'focus:ring-2 focus:ring-brand/10',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    borderColor: 'var(--bg-border)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
            </div>

            {/* Issue Number */}
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary">
                <Hash className="h-3.5 w-3.5" />
                {t.input.issueLabel}
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-text-muted select-none">
                  #
                </span>
                <input
                  type="number"
                  value={issue}
                  onChange={e => setIssue(e.target.value)}
                  placeholder={t.input.issuePlaceholder}
                  min="1"
                  disabled={isRunning}
                  className={cn(
                    'w-full rounded-lg border pl-8 pr-4 py-2.5 text-sm',
                    'placeholder:text-text-muted font-mono',
                    'outline-none transition-all',
                    'focus:ring-2 focus:ring-brand/10',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    borderColor: 'var(--bg-border)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
            </div>
          </div>

          {/* 按钮区 */}
          <div className="flex items-center gap-3 pt-1">
            {/* 主按钮 */}
            <button
              type="submit"
              disabled={isRunning || !repo.trim() || !issue.trim()}
              className={cn(
                'relative flex flex-1 items-center justify-center gap-2 overflow-hidden',
                'rounded-lg px-6 py-2.5 text-sm font-semibold',
                'transition-all duration-200',
                isRunning
                  ? 'cursor-not-allowed bg-brand/20 text-brand-glow border border-brand/20'
                  : 'bg-gradient-to-r from-brand-dim to-brand text-white',
                !isRunning && 'hover:from-brand hover:to-accent-purple hover:shadow-glow-brand',
                'disabled:opacity-60',
              )}
            >
              {!isRunning && (
                <span className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
              )}
              {isRunning ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t.input.agentWorking}
                </>
              ) : (
                <>
                  <Rocket className="h-4 w-4" />
                  {t.input.startBtn}
                </>
              )}
            </button>

            {/* 预览按钮 */}
            {!isRunning && (
              <button
                type="button"
                onClick={() => onPreview({ repoUrl: repo.trim(), issueNumber: issue.trim() })}
                disabled={!repo.trim() || !issue.trim() || previewStatus === 'loading'}
                className="flex items-center gap-1.5 rounded-lg border px-4 py-2.5 text-sm transition-all hover:border-brand/30 hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  borderColor:     'var(--bg-border)',
                  backgroundColor: 'var(--bg-card)',
                  color:           'var(--text-secondary)',
                }}
              >
                {previewStatus === 'loading'
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Eye className="h-3.5 w-3.5" />
                }
                {t.input.previewBtn}
              </button>
            )}

            {/* 重置按钮 */}
            {isDone && (
              <button
                type="button"
                onClick={onReset}
                className="flex items-center gap-1.5 rounded-lg border px-4 py-2.5 text-sm transition-all hover:border-brand/30 hover:text-text-primary animate-fade-in"
                style={{
                  borderColor: 'var(--bg-border)',
                  backgroundColor: 'var(--bg-card)',
                  color: 'var(--text-secondary)',
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                {t.input.resetBtn}
              </button>
            )}
          </div>
        </form>
      </div>
    </section>
  )
}
