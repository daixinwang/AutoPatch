import { SquarePen, PanelLeftClose, Zap } from 'lucide-react'
import { cn } from '../lib/utils'
import type { HistoryRecord } from '../types'

interface SidebarProps {
  records: HistoryRecord[]
  selectedId: string | null
  onNewFix: () => void
  onSelect: (id: string) => void
  onCollapse: () => void
}

function relativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

function repoShortName(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '')
}

export default function Sidebar({ records, selectedId, onNewFix, onSelect, onCollapse }: SidebarProps) {
  return (
    <aside
      className="flex flex-col flex-shrink-0 border-r border-bg-border transition-colors"
      style={{
        width: 240,
        height: '100vh',
        position: 'sticky',
        top: 0,
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      {/* 顶部工具栏：logo + 折叠按钮（与 Header 等高） */}
      <div className="flex h-14 flex-shrink-0 items-center justify-between px-3">
        {/* Logo */}
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg"
          style={{ backgroundColor: 'var(--bg-card)' }}
        >
          <Zap className="h-4 w-4 text-brand" />
        </div>
        {/* 折叠按钮 */}
        <button
          onClick={onCollapse}
          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
          title="折叠侧边栏"
        >
          <PanelLeftClose className="h-5 w-5" />
        </button>
      </div>

      {/* New Fix 按钮 */}
      <div className="px-2 pb-2">
        <button
          onClick={onNewFix}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover active:opacity-70"
        >
          <SquarePen className="h-4 w-4 flex-shrink-0" />
          New Fix
        </button>
      </div>

      {/* 历史记录列表 */}
      <div className="flex-1 overflow-y-auto py-2">
        {records.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-text-muted">
            暂无历史记录
          </p>
        ) : (
          records.map(record => (
            <button
              key={record.id}
              onClick={() => onSelect(record.id)}
              className={cn(
                'flex w-full flex-col gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-bg-hover',
                selectedId === record.id && 'bg-bg-card',
              )}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                {/* 状态圆点 */}
                <span
                  className={cn(
                    'h-1.5 w-1.5 flex-shrink-0 rounded-full',
                    record.status === 'success' ? 'bg-accent-green' : 'bg-accent-red',
                  )}
                />
                {/* 仓库 + Issue */}
                <span className="truncate text-xs font-medium text-text-primary">
                  {repoShortName(record.repoUrl)} #{record.issueNumber}
                </span>
              </div>
              {/* 相对时间 */}
              <span className="pl-3 text-xs text-text-muted">
                {relativeTime(record.timestamp)}
              </span>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}
