import { Loader2, RotateCcw, Eye } from 'lucide-react'
import { cn } from '../lib/utils'
import { useT } from '../contexts/LanguageContext'
import type { PatchInput, TaskStatus } from '../types'
import type { PreviewStatus } from '../hooks/useIssuePreview'

interface Props {
  status:        TaskStatus
  repo:          string
  issue:         string
  onRepoChange:  (v: string) => void
  onIssueChange: (v: string) => void
  onSubmit:      (input: PatchInput) => void
  onReset:       () => void
  onPreview:     (input: PatchInput) => void
  previewStatus: PreviewStatus
}

export default function InputSection({ status, repo, issue, onRepoChange, onIssueChange, onSubmit, onReset, onPreview, previewStatus }: Props) {
  const t = useT()

  const isRunning = status === 'running'
  const isDone    = status === 'success' || status === 'failed'
  const canSubmit = !!repo.trim() && !!issue.trim()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    onSubmit({ repoUrl: repo.trim(), issueNumber: issue.trim() })
  }

  return (
    <section className="animate-slide-up w-full">
      <form onSubmit={handleSubmit}>
        <div
          className="flex items-center overflow-hidden rounded-xl border transition-all focus-within:ring-2 focus-within:ring-brand/15"
          style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-card)' }}
        >
          {/* Repo 输入（弹性伸缩，占大部分空间） */}
          <div className="flex flex-[3] items-center min-w-0 px-3">
            <span className="shrink-0 text-sm text-text-muted select-none pr-1">
              {t.input.repoPrefix}
            </span>
            <input
              type="text"
              value={repo}
              onChange={e => onRepoChange(e.target.value)}
              placeholder={t.input.repoPlaceholder}
              disabled={isRunning}
              className={cn(
                'flex-1 min-w-0 bg-transparent py-4 text-base font-mono outline-none',
                'placeholder:text-text-muted',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
              style={{ color: 'var(--text-primary)' }}
            />
          </div>

          {/* 竖向分隔线 */}
          <div className="h-5 w-px shrink-0" style={{ backgroundColor: 'var(--bg-border)' }} />

          {/* Issue 输入（自适应，可压缩，最小 64px） */}
          <div className="flex flex-[1] items-center min-w-[64px] px-3">
            <span className="shrink-0 text-sm text-text-muted select-none pr-1">#</span>
            <input
              type="number"
              value={issue}
              onChange={e => onIssueChange(e.target.value)}
              placeholder={t.input.issuePlaceholder}
              min="1"
              disabled={isRunning}
              className={cn(
                'w-full min-w-0 bg-transparent py-4 text-base font-mono outline-none',
                'placeholder:text-text-muted',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                // 隐藏数字输入的上下箭头
                '[appearance:textfield]',
                '[&::-webkit-outer-spin-button]:appearance-none',
                '[&::-webkit-inner-spin-button]:appearance-none',
              )}
              style={{ color: 'var(--text-primary)' }}
            />
          </div>

          {/* 竖向分隔线 */}
          <div className="h-5 w-px shrink-0" style={{ backgroundColor: 'var(--bg-border)' }} />

          {/* 按钮区：状态驱动，同一位置切换 */}
          <div className="flex shrink-0 items-center gap-1 px-2">
            {isRunning ? (
              /* 运行中：仅显示 loading 指示，不可点击 */
              <div className="flex items-center gap-1.5 px-3 py-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span className="hidden sm:inline">{t.input.agentWorking}</span>
              </div>
            ) : isDone ? (
              /* 完成后：重置按钮 */
              <button
                type="button"
                onClick={onReset}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-all hover:border-brand/30 hover:text-text-primary animate-fade-in"
                style={{ borderColor: 'var(--bg-border)', backgroundColor: 'transparent', color: 'var(--text-secondary)' }}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{t.input.resetBtn}</span>
              </button>
            ) : (
              /* 默认：预览按钮（始终显示，不因预览成功而切换） */
              <button
                type="button"
                onClick={() => onPreview({ repoUrl: repo.trim(), issueNumber: issue.trim() })}
                disabled={!canSubmit || previewStatus === 'loading'}
                className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-all hover:border-brand/30 hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ borderColor: 'var(--bg-border)', backgroundColor: 'transparent', color: 'var(--text-secondary)' }}
              >
                {previewStatus === 'loading'
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Eye className="h-3.5 w-3.5" />
                }
                <span className="hidden sm:inline">{t.input.previewBtn}</span>
              </button>
            )}
          </div>
        </div>
      </form>
    </section>
  )
}
