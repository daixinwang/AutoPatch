import { useState } from 'react'
import Header             from './components/Header'
import InputSection       from './components/InputSection'
import WorkflowVisualizer from './components/WorkflowVisualizer'
import TerminalWindow     from './components/TerminalWindow'
import ResultArea         from './components/ResultArea'
import { usePatchTask }   from './hooks/usePatchTask'
import { useTheme }       from './hooks/useTheme'
import type { PatchInput } from './types'

export default function App() {
  const { mode: themeMode, setMode: setThemeMode } = useTheme()
  const { status, nodes, logs, result, startTask, reset } = usePatchTask()

  const [lastInput, setLastInput] = useState<PatchInput>({
    repoUrl: 'daixinwang/AutoPatch',
    issueNumber: '42',
  })

  function handleSubmit(input: PatchInput) {
    setLastInput(input)
    startTask(input)
  }

  const showWorkflow = status !== 'idle'
  const showResult   = status === 'success' && result !== null

  return (
    <div className="min-h-screen bg-grid-pattern transition-colors" style={{ backgroundColor: 'var(--bg-base)' }}>
      {/* 顶部渐变光晕 */}
      <div className="pointer-events-none fixed inset-x-0 top-0 h-72 bg-gradient-radial from-brand/8 via-transparent to-transparent" />

      <Header themeMode={themeMode} onThemeChange={setThemeMode} />

      <main className="mx-auto max-w-4xl space-y-5 px-6 py-10">
        {/* Hero 文案 */}
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl" style={{ color: 'var(--text-primary)' }}>
            Fix GitHub Issues{' '}
            <span className="text-gradient">Automatically</span>
          </h1>
          <p className="mt-3 text-sm text-text-secondary max-w-xl mx-auto">
            Multi-agent pipeline powered by LangGraph — Planner analyzes, Coder fixes,
            TestRunner validates, Reviewer approves.
          </p>
        </div>

        {/* 输入区 */}
        <InputSection status={status} onSubmit={handleSubmit} onReset={reset} />

        {/* Agent 工作流可视化 */}
        {showWorkflow && <WorkflowVisualizer nodes={nodes} />}

        {/* 终端日志窗口（任务进行中始终显示） */}
        {showWorkflow && <TerminalWindow logs={logs} />}

        {/* 结果区 */}
        {showResult && (
          <ResultArea
            result={result}
            repoUrl={lastInput.repoUrl}
            issue={lastInput.issueNumber}
          />
        )}
      </main>

      {/* 底部装饰 */}
      <footer className="mt-20 border-t border-bg-border py-6 text-center text-xs text-text-muted">
        AutoPatch · Built with LangGraph + React · Open Source
      </footer>
    </div>
  )
}
