import { SquarePen, PanelLeftClose, PanelLeftOpen, Zap } from 'lucide-react'
import { cn } from '../lib/utils'
import { useT } from '../contexts/LanguageContext'
import type { HistoryRecord } from '../types'

interface SidebarProps {
  records: HistoryRecord[]
  selectedId: string | null
  onNewFix: () => void
  onSelect: (id: string) => void
  onCollapse: () => void
  collapsed: boolean
  onExpand: () => void
}

function repoShortName(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '')
}

export default function Sidebar({ records, selectedId, onNewFix, onSelect, onCollapse, collapsed, onExpand }: SidebarProps) {
  const t = useT()
  return (
    <aside
      className="flex flex-col flex-shrink-0 border-r border-bg-border transition-all duration-200"
      style={{
        width: collapsed ? 56 : 240,
        height: '100vh',
        position: 'sticky',
        top: 0,
        overflow: 'hidden',
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      {collapsed ? (
        /* ── 收起状态：仅显示 logo + 新建图标 ── */
        <>
          {/* Logo（悬浮变展开图标） */}
          <div className="flex h-14 flex-shrink-0 items-center justify-center">
            <button
              onClick={onExpand}
              className="group relative flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-bg-hover"
              style={{ backgroundColor: 'var(--bg-card)' }}
              title={t.sidebar.expand}
            >
              <Zap className="h-4 w-4 text-brand transition-opacity group-hover:opacity-0" />
              <PanelLeftOpen className="absolute h-4 w-4 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          </div>

          {/* 新建修复图标 */}
          <div className="flex items-center justify-center pb-2">
            <button
              onClick={onNewFix}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
              title={t.sidebar.newFix}
            >
              <SquarePen className="h-4 w-4" />
            </button>
          </div>
        </>
      ) : (
        /* ── 展开状态：完整侧边栏 ── */
        <>
          {/* 顶部工具栏：logo + 折叠按钮（与 Header 等高） */}
          <div className="flex h-14 flex-shrink-0 items-center justify-between px-3">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-lg"
              style={{ backgroundColor: 'var(--bg-card)' }}
            >
              <Zap className="h-4 w-4 text-brand" />
            </div>
            <button
              onClick={onCollapse}
              className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
              title={t.sidebar.collapse}
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
              {t.sidebar.newFix}
            </button>
          </div>

          {/* 历史记录列表 */}
          <div className="flex-1 overflow-y-auto py-2">
            {records.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-text-muted">
                {t.sidebar.noHistory}
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
                    <span
                      className={cn(
                        'h-1.5 w-1.5 flex-shrink-0 rounded-full',
                        record.status === 'success' ? 'bg-accent-green' : 'bg-accent-red',
                      )}
                    />
                    <span className="truncate text-xs font-medium text-text-primary">
                      {repoShortName(record.repoUrl)} #{record.issueNumber}
                    </span>
                  </div>
                  <span className="pl-3 text-xs text-text-muted">
                    {t.sidebar.relativeTime(record.timestamp)}
                  </span>
                </button>
              ))
            )}
          </div>
        </>
      )}
    </aside>
  )
}
