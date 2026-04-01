import { Github, Zap, ExternalLink } from 'lucide-react'

export default function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-bg-border bg-bg-base/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dim shadow-glow-brand">
            <Zap className="h-4 w-4 text-white" strokeWidth={2.5} />
            {/* 发光光晕 */}
            <span className="absolute inset-0 rounded-lg animate-pulse-slow opacity-40 bg-brand blur-sm" />
          </div>
          <span className="text-lg font-semibold tracking-tight text-text-primary">
            Auto<span className="text-gradient">Patch</span>
          </span>
          {/* AI 徽章 */}
          <span className="flex items-center gap-1 rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-[11px] font-medium text-brand-glow">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-green animate-pulse" />
            AI Agent
          </span>
        </div>

        {/* 右侧操作 */}
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-text-muted sm:block">
            Powered by LangGraph
          </span>
          <a
            href="https://github.com/daixinwang/AutoPatch"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-bg-border bg-bg-card px-3 py-1.5 text-xs text-text-secondary transition-all hover:border-brand/30 hover:text-text-primary hover:shadow-card"
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
