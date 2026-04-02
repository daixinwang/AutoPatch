import { Github, Zap, ExternalLink, Sun, Moon, Monitor } from 'lucide-react'
import { cn } from '../lib/utils'
import type { ThemeMode } from '../hooks/useTheme'

interface Props {
  themeMode:    ThemeMode
  onThemeChange: (mode: ThemeMode) => void
}

const THEME_OPTIONS: { mode: ThemeMode; icon: React.ReactNode; label: string }[] = [
  { mode: 'light',  icon: <Sun     className="h-3.5 w-3.5" />, label: 'Light'  },
  { mode: 'system', icon: <Monitor className="h-3.5 w-3.5" />, label: 'System' },
  { mode: 'dark',   icon: <Moon    className="h-3.5 w-3.5" />, label: 'Dark'   },
]

export default function Header({ themeMode, onThemeChange }: Props) {
  return (
    <header
      className="sticky top-0 z-50 border-b border-bg-border backdrop-blur-xl transition-colors"
      style={{ backgroundColor: 'var(--bg-base-alpha)' }}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dim shadow-glow-brand">
            <Zap className="h-4 w-4 text-white" strokeWidth={2.5} />
            <span className="absolute inset-0 rounded-lg animate-pulse-slow opacity-40 bg-brand blur-sm" />
          </div>
          <span className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            Auto<span className="text-gradient">Patch</span>
          </span>
          <span className="flex items-center gap-1 rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-[11px] font-medium text-brand-glow">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-green animate-pulse" />
            AI Agent
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

          <span className="hidden text-xs text-text-muted sm:block">
            Powered by LangGraph
          </span>
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
