import { Github, ExternalLink, Sun, Moon, Monitor, PanelLeftOpen } from 'lucide-react'
import { cn } from '../lib/utils'
import type { ThemeMode } from '../hooks/useTheme'

interface Props {
  themeMode:       ThemeMode
  onThemeChange:   (mode: ThemeMode) => void
  sidebarOpen:     boolean
  onToggleSidebar: () => void
}

const THEME_OPTIONS: { mode: ThemeMode; icon: React.ReactNode; label: string }[] = [
  { mode: 'light',  icon: <Sun     className="h-3.5 w-3.5" />, label: 'Light'  },
  { mode: 'system', icon: <Monitor className="h-3.5 w-3.5" />, label: 'System' },
  { mode: 'dark',   icon: <Moon    className="h-3.5 w-3.5" />, label: 'Dark'   },
]

export default function Header({ themeMode, onThemeChange, sidebarOpen, onToggleSidebar }: Props) {
  return (
    <header
      className="sticky top-0 z-50 backdrop-blur-xl transition-colors"
      style={{ backgroundColor: 'var(--bg-base-alpha)' }}
    >
      <div className="flex h-14 items-center justify-between px-4">
        {/* 左侧：展开按钮（折叠时显示）+ 标题 */}
        <div className="flex items-center gap-2">
          {!sidebarOpen && (
            <button
              onClick={onToggleSidebar}
              className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
              title="展开侧边栏"
            >
              <PanelLeftOpen className="h-5 w-5" />
            </button>
          )}
          <span className="text-xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            AutoPatch
          </span>
        </div>

        {/* 右侧操作 */}
        <div className="flex items-center gap-3">
          {/* 主题切换三档按钮 */}
          <div
            className="flex items-center rounded-lg border p-0.5 gap-0.5 transition-colors"
            style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
          >
            {THEME_OPTIONS.map(({ mode, icon, label }) => (
              <button
                key={mode}
                title={label}
                onClick={() => onThemeChange(mode)}
                className={cn(
                  'flex items-center justify-center rounded-md p-1.5 transition-all duration-150',
                  themeMode === mode
                    ? 'bg-brand text-white shadow-sm'
                    : 'text-text-muted hover:text-text-primary',
                )}
                style={themeMode !== mode ? { ':hover': { backgroundColor: 'var(--bg-hover)' } } as React.CSSProperties : undefined}
              >
                {icon}
              </button>
            ))}
          </div>

          <a
            href="https://github.com/daixinwang/AutoPatch"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-all hover:border-brand/30 hover:text-text-primary hover:shadow-card"
            style={{
              borderColor: 'var(--bg-border)',
              backgroundColor: 'var(--bg-card)',
              color: 'var(--text-secondary)',
            }}
          >
            <Github className="h-3.5 w-3.5" />
            <span>GitHub</span>
            <ExternalLink className="h-3 w-3 opacity-50" />
          </a>
        </div>
      </div>
    </header>
  )
}
