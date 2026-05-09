import { Sun, Moon, Monitor, PanelLeftOpen } from 'lucide-react'
import { cn } from '../lib/utils'
import { useT } from '../contexts/LanguageContext'
import type { ThemeMode } from '../hooks/useTheme'
import type { Lang } from '../hooks/useLanguage'

interface Props {
  themeMode:       ThemeMode
  onThemeChange:   (mode: ThemeMode) => void
  sidebarOpen:     boolean
  onToggleSidebar: () => void
  lang:            Lang
  onLangChange:    (lang: Lang) => void
}

const THEME_OPTIONS: { mode: ThemeMode; icon: React.ReactNode }[] = [
  { mode: 'light',  icon: <Sun     className="h-3.5 w-3.5" /> },
  { mode: 'system', icon: <Monitor className="h-3.5 w-3.5" /> },
  { mode: 'dark',   icon: <Moon    className="h-3.5 w-3.5" /> },
]

const LANG_OPTIONS: { value: Lang; label: string }[] = [
  { value: 'zh', label: '中' },
  { value: 'en', label: 'EN' },
]

export default function Header({ themeMode, onThemeChange, sidebarOpen, onToggleSidebar, lang, onLangChange }: Props) {
  const t = useT()

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
              title={t.sidebar.expand}
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
          {/* 主题切换 */}
          <div
            className="flex items-center rounded-lg border p-0.5 gap-0.5 transition-colors"
            style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
          >
            {THEME_OPTIONS.map(({ mode, icon }) => (
              <button
                key={mode}
                title={t.header[`theme${mode.charAt(0).toUpperCase() + mode.slice(1)}` as keyof typeof t.header]}
                onClick={() => onThemeChange(mode)}
                className={cn(
                  'flex items-center justify-center rounded-md p-1.5 transition-all duration-150',
                  themeMode === mode
                    ? 'bg-brand text-white shadow-sm'
                    : 'text-text-muted hover:text-text-primary',
                )}
              >
                {icon}
              </button>
            ))}
          </div>

          {/* 语言切换 */}
          <div
            className="flex items-center rounded-lg border p-0.5 gap-0.5 transition-colors"
            style={{ borderColor: 'var(--bg-border)', backgroundColor: 'var(--bg-surface)' }}
          >
            {LANG_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => onLangChange(value)}
                className={cn(
                  'rounded-md px-2 py-1 text-xs font-medium transition-all duration-150',
                  lang === value
                    ? 'bg-brand text-white shadow-sm'
                    : 'text-text-muted hover:text-text-primary',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  )
}
