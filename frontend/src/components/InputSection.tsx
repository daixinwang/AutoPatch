import { useState } from 'react'
import { Rocket, Loader2, RotateCcw, Eye } from 'lucide-react'
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
    <section className="animate-slide-up w-full">
      <form onSubmit={handleSubmit}>
        {/* 单行输入 bar */}
        <div
          className="flex items-center gap-0 overflow-hidden rounded-xl border transition-all focus-within:ring-2 focus-within:ring-brand/15"
          style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-card)' }}
        >
          {/* Repo 输入 */}
          <div className="flex flex-1 items-center min-w-0 px-3">
            <span className="shrink-0 text-xs text-text-muted select-none pr-1">
              {t.input.repoPrefix}
            </span>
            <input
              type="text"
              value={repo}
              onChange={e => setRepo(e.target.value)}
              placeholder={t.input.repoPlaceholder}
              disabled={isRunning}
              className={cn(
                'flex-1 min-w-0 bg-transparent py-3 text-sm font-mono outline-none',
                'placeholder:text-text-muted',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
              style={{ color: 'var(--text-primary)' }}
            />
          </div>

          {/* 竖向分隔线 */}
          <div className="h-5 w-px flex-shrink-0" style={{ backgroundColor: 'var(--bg-border)' }} />

          {/* Issue 输入 */}
          <div className="flex items-center px-3 w-28 flex-shrink-0">
            <span className="shrink-0 text-xs text-text-muted select-none pr-1">#</span>
            <input
              type="number"
              value={issue}
              onChange={e => setIssue(e.target.value)}
              placeholder={t.input.issuePlaceholder}
              min="1"
              disabled={isRunning}
              className={cn(
                'w-full bg-transparent py-3 text-sm font-mono outline-none',
                'placeholder:text-text-muted',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
              style={{ color: 'var(--text-primary)' }}
            />
          </div>

          {/* 竖向分隔线 */}
          <div className="h-5 w-px flex-shrink-0" style={{ backgroundColor: 'var(--bg-border)' }} />

          {/* 按钮区 */}
          <div className="flex items-center gap-1 px-2 flex-shrink-0">
            {/* Start / Running 按钮 */}
            <button
              type="submit"
              disabled={isRunning || !repo.trim() || !issue.trim()}
              className={cn(
                'relative flex items-center gap-1.5 overflow-hidden rounded-lg px-3 py-1.5 text-sm font-medium',
                'transition-all duration-200',
                isRunning
                  ? 'cursor-not-allowed text-brand-glow'
                  : 'bg-brand text-white hover:bg-brand-dim',
                'disabled:opacity-60',
              )}
            >
              {!isRunning && (
                <span className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
              )}
              {isRunning
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Rocket className="h-3.5 w-3.5" />
              }
              <span className="hidden sm:inline">
                {isRunning ? t.input.agentWorking : t.input.startBtn}
              </span>
            </button>

            {/* 预览按钮 */}
            {!isRunning && (
              <button
                type="button"
                onClick={() => onPreview({ repoUrl: repo.trim(), issueNumber: issue.trim() })}
                disabled={!repo.trim() || !issue.trim() || previewStatus === 'loading'}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-all hover:border-brand/30 hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  borderColor:     'var(--bg-border)',
                  backgroundColor: 'transparent',
                  color:           'var(--text-secondary)',
                }}
              >
                {previewStatus === 'loading'
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Eye className="h-3.5 w-3.5" />
                }
                <span className="hidden sm:inline">{t.input.previewBtn}</span>
              </button>
            )}

            {/* 重置按钮 */}
            {isDone && (
              <button
                type="button"
                onClick={onReset}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-all hover:border-brand/30 hover:text-text-primary animate-fade-in"
                style={{
                  borderColor:     'var(--bg-border)',
                  backgroundColor: 'transparent',
                  color:           'var(--text-secondary)',
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{t.input.resetBtn}</span>
              </button>
            )}
          </div>
        </div>
      </form>
    </section>
  )
}
