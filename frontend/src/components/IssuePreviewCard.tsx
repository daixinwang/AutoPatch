import { CircleDot, Tag, Code2, Star, MessageSquare, ExternalLink, Rocket } from 'lucide-react'
import { cn } from '../lib/utils'
import { useT } from '../contexts/LanguageContext'
import type { IssuePreview } from '../types'

interface Props {
  preview:         IssuePreview
  onStartPipeline: () => void
}

export default function IssuePreviewCard({ preview, onStartPipeline }: Props) {
  const t = useT()
  const isOpen = preview.issueState === 'open'

  return (
    <section className="animate-slide-up">
      <div className="card-gradient-border p-5 space-y-4">
        {/* 标题 + 状态 */}
        <div className="flex items-start justify-between gap-3">
          <h3 className="flex-1 min-w-0 text-base font-semibold leading-snug"
            style={{ color: 'var(--text-primary)' }}>
            {preview.issueTitle}
          </h3>
          <span className={cn(
            'flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
            isOpen
              ? 'bg-accent-green/15 text-accent-green'
              : 'bg-text-muted/15 text-text-muted',
          )}>
            <CircleDot className="h-3 w-3" />
            {isOpen ? t.issue.open : t.issue.closed}
          </span>
        </div>

        {/* 标签 */}
        {preview.issueLabels.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {preview.issueLabels.map(label => (
              <span key={label}
                className="flex items-center gap-1 rounded border px-2 py-0.5 text-[11px]"
                style={{
                  borderColor:     'var(--bg-border)',
                  backgroundColor: 'var(--bg-surface)',
                  color:           'var(--text-secondary)',
                }}>
                <Tag className="h-2.5 w-2.5" />
                {label}
              </span>
            ))}
          </div>
        )}

        {/* Issue 正文 */}
        <div className="rounded-lg p-3 max-h-48 overflow-y-auto"
          style={{ backgroundColor: 'var(--bg-surface)' }}>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed"
            style={{ color: 'var(--text-secondary)' }}>
            {preview.issueBody || t.issue.noBody}
          </pre>
        </div>

        {/* 元数据 + GitHub 链接 */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-1 border-t"
          style={{ borderColor: 'var(--bg-border)' }}>
          {preview.repoLanguage && preview.repoLanguage !== 'Unknown' && (
            <MetaItem icon={<Code2 className="h-3 w-3" />} value={preview.repoLanguage} />
          )}
          <MetaItem icon={<Star className="h-3 w-3" />} value={String(preview.repoStars)} />
          <MetaItem icon={<MessageSquare className="h-3 w-3" />} value={t.issue.comments(preview.commentCount)} />
          <a
            href={preview.issueUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-1 text-xs text-brand hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            {t.issue.viewOnGitHub}
          </a>
        </div>

        {/* 确认启动按钮 */}
        <button
          type="button"
          onClick={onStartPipeline}
          className={cn(
            'relative w-full flex items-center justify-center gap-2 overflow-hidden',
            'rounded-lg px-6 py-2.5 text-sm font-semibold text-white',
            'bg-gradient-to-r from-brand-dim to-brand',
            'transition-all duration-200',
            'hover:from-brand hover:to-accent-purple hover:shadow-glow-brand',
          )}
        >
          <span className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          <Rocket className="h-4 w-4" />
          {t.issue.confirmStart}
        </button>
      </div>
    </section>
  )
}

function MetaItem({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
      {icon}
      {value}
    </span>
  )
}
