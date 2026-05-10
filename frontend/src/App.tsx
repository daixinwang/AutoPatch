import { useState, useEffect, useRef } from 'react'
import Header             from './components/Header'
import InputSection       from './components/InputSection'
import IssuePreviewCard   from './components/IssuePreviewCard'
import TerminalWindow     from './components/TerminalWindow'
import ResultArea         from './components/ResultArea'
import Sidebar            from './components/Sidebar'
import { usePatchTask }   from './hooks/usePatchTask'
import { useTheme }       from './hooks/useTheme'
import { useIssuePreview } from './hooks/useIssuePreview'
import { useHistory }     from './hooks/useHistory'
import { useLanguage }    from './hooks/useLanguage'
import { LanguageContext } from './contexts/LanguageContext'
import { zh }             from './i18n/zh'
import { en }             from './i18n/en'
import type { PatchInput, HistoryRecord } from './types'

export default function App() {
  const { mode: themeMode, setMode: setThemeMode } = useTheme()
  const { status, logs, result, startTask, reset } = usePatchTask()
  const { previewStatus, preview, previewError, fetchPreview, clearPreview } = useIssuePreview()
  const { records, addRecord } = useHistory()
  const { lang, setLang } = useLanguage()
  const locale = lang === 'zh' ? zh : en

  const [lastInput, setLastInput] = useState<PatchInput>({
    repoUrl: 'daixinwang/AutoPatch',
    issueNumber: '42',
  })

  function handleRepoChange(v: string)  { setLastInput(p => ({ ...p, repoUrl: v })) }
  function handleIssueChange(v: string) { setLastInput(p => ({ ...p, issueNumber: v })) }
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // 任务完成后自动存入历史记录
  const savedRef = useRef<string | null>(null)
  useEffect(() => {
    if ((status === 'success' || status === 'failed') && result !== null) {
      // 避免同一结果重复写入（strict mode 双调用）
      const key = `${lastInput.repoUrl}/${lastInput.issueNumber}/${result.elapsedMs}`
      if (savedRef.current === key) return
      savedRef.current = key

      const record: HistoryRecord = {
        id: crypto.randomUUID(),
        timestamp: Date.now(),
        repoUrl: lastInput.repoUrl,
        issueNumber: lastInput.issueNumber,
        status: status === 'success' ? 'success' : 'failed',
        result,
        issuePreview: preview ?? undefined,
      }
      addRecord(record)
    }
  }, [status, result])

  function handleSubmit(input: PatchInput) {
    setLastInput(input)
    clearPreview()
    setSelectedHistoryId(null)
    startTask(input)
  }

  function handlePreview(input: PatchInput) {
    setLastInput(input)
    fetchPreview(input)
  }

  function handleNewFix() {
    setSelectedHistoryId(null)
    reset()
    clearPreview()
  }

  const showWorkflow   = status !== 'idle' && selectedHistoryId === null
  const showResult     = status === 'success' && result !== null && selectedHistoryId === null
  const showPreview    = preview !== null && status === 'idle' && selectedHistoryId === null
  const showPreviewErr = previewStatus === 'error' && status === 'idle' && selectedHistoryId === null

  const selectedRecord = selectedHistoryId
    ? records.find(r => r.id === selectedHistoryId) ?? null
    : null

  return (
    <LanguageContext.Provider value={locale}>
    <div
      className="flex h-screen overflow-hidden bg-grid-pattern transition-colors"
      style={{ backgroundColor: 'var(--bg-base)' }}
    >
      {/* 顶部渐变光晕 */}
      <div className="pointer-events-none fixed inset-x-0 top-0 h-72 bg-gradient-radial from-brand/8 via-transparent to-transparent" />

      {/* 左侧侧边栏（带折叠动画） */}
      <div
        className="flex-shrink-0 overflow-hidden transition-all duration-200"
        style={{ width: sidebarOpen ? 240 : 0 }}
      >
        <Sidebar
          records={records}
          selectedId={selectedHistoryId}
          onNewFix={handleNewFix}
          onSelect={setSelectedHistoryId}
          onCollapse={() => setSidebarOpen(false)}
        />
      </div>

      {/* 右侧主内容 */}
      <div className="flex flex-1 flex-col min-w-0 overflow-y-auto">
        <Header
          themeMode={themeMode}
          onThemeChange={setThemeMode}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(o => !o)}
          lang={lang}
          onLangChange={setLang}
        />

        <main className="flex flex-1 flex-col px-6">
          {selectedRecord ? (
            /* 历史查看视图 — 顶部对齐 */
            <div className="mx-auto w-full max-w-3xl space-y-5 py-10">
              <div
                className="flex items-center gap-2 text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                <span className="font-medium text-text-primary">
                  {selectedRecord.repoUrl.replace(/^https?:\/\/github\.com\//, '')}
                </span>
                <span>·</span>
                <span>Issue #{selectedRecord.issueNumber}</span>
              </div>
              <ResultArea
                result={selectedRecord.result}
                repoUrl={selectedRecord.repoUrl}
                issue={selectedRecord.issueNumber}
              />
            </div>
          ) : status === 'idle' ? (
            /* 空闲态 — GPT 比例：顶部弹性 2 : 内容块 : 底部弹性 3
               内容块中心落在可用高度约 40% 处，与 ChatGPT 视觉比例一致 */
            <div className="flex flex-1 flex-col items-center px-6">
              {/* 顶部弹性区（2份） */}
              <div style={{ flex: 2 }} />

              {/* 内容块：提示文字 + 输入框 */}
              <div className="w-full max-w-3xl flex flex-col gap-10">
                <p className="text-center text-xl font-normal tracking-tight" style={{ color: 'var(--text-primary)' }}>
                  {locale.app.greetingSub}
                </p>
                <div className="space-y-4">
                  <InputSection
                    status={status}
                    repo={lastInput.repoUrl}
                    issue={lastInput.issueNumber}
                    onRepoChange={handleRepoChange}
                    onIssueChange={handleIssueChange}
                    onSubmit={handleSubmit}
                    onReset={reset}
                    onPreview={handlePreview}
                    previewStatus={previewStatus}
                  />
                  {showPreviewErr && (
                    <div className="card-gradient-border px-4 py-3 text-sm text-accent-red animate-slide-up">
                      {locale.app.previewFailed(previewError ?? '')}
                    </div>
                  )}
                  {showPreview && (
                    <IssuePreviewCard
                      preview={preview}
                      onStartPipeline={() => handleSubmit(lastInput)}
                    />
                  )}
                </div>
              </div>

              {/* 底部弹性区（3份） */}
              <div style={{ flex: 3 }} />
            </div>
          ) : (
            /* 运行中 / 结果 — 顶部对齐 */
            <div className="mx-auto w-full max-w-3xl space-y-5 py-10">
              <InputSection
                status={status}
                repo={lastInput.repoUrl}
                issue={lastInput.issueNumber}
                onRepoChange={handleRepoChange}
                onIssueChange={handleIssueChange}
                onSubmit={handleSubmit}
                onReset={reset}
                onPreview={handlePreview}
                previewStatus={previewStatus}
              />
              {showPreviewErr && (
                <div className="card-gradient-border px-4 py-3 text-sm text-accent-red animate-slide-up">
                  {locale.app.previewFailed(previewError ?? '')}
                </div>
              )}
              {showWorkflow && <TerminalWindow logs={logs} />}
              {showResult && (
                <ResultArea
                  result={result}
                  repoUrl={lastInput.repoUrl}
                  issue={lastInput.issueNumber}
                />
              )}
            </div>
          )}
        </main>

      </div>
    </div>
    </LanguageContext.Provider>
  )
}
