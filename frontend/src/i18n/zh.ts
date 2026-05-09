export const zh = {
  sidebar: {
    newFix:   'New Fix',
    noHistory: '暂无历史记录',
    collapse:  '折叠侧边栏',
    expand:    '展开侧边栏',
    relativeTime(ts: number): string {
      const diff = Date.now() - ts
      const m = Math.floor(diff / 60_000)
      if (m < 1)  return '刚刚'
      if (m < 60) return `${m} 分钟前`
      const h = Math.floor(m / 60)
      if (h < 24) return `${h} 小时前`
      return `${Math.floor(h / 24)} 天前`
    },
  },
  header: {
    themeLight:  'Light',
    themeSystem: 'System',
    themeDark:   'Dark',
  },
  input: {
    sectionTitle:    'CONFIGURE TARGET',
    repoLabel:       'GitHub Repository',
    repoPrefix:      'github.com/',
    repoPlaceholder: 'owner/repo',
    issueLabel:      'Issue Number',
    issuePlaceholder:'42',
    agentWorking:    'Agent is working...',
    startBtn:        'Start Auto-Fix',
    previewBtn:      '预览',
    resetBtn:        '重置',
    cancelBtn:       '取消',
  },
  terminal: {
    shellTitle: 'autopatch — bash',
    waiting:    'Waiting for task input...',
    linesUnit:  'lines',
  },
  result: {
    successTitle: 'Patch Generated Successfully',
    failTitle:    'Review Failed',
    added:        'Added',
    removed:      'Removed',
    steps:        'Steps',
    time:         'Time',
    changed:      'Changed:',
    viewPR:       'View PR',
    createPR:     'Create PR',
    creating:     'Creating…',
    copied:       'Copied!',
    copyDiff:     'Copy Diff',
    applyPatch:   'Apply patch:',
    prError:      (msg: string) => `PR 创建失败：${msg}`,
  },
  issue: {
    open:         'Open',
    closed:       'Closed',
    noBody:       '（暂无正文）',
    comments:     (n: number) => `${n} 条评论`,
    viewOnGitHub: '在 GitHub 查看',
    confirmStart: 'Confirm & Start Auto-Fix',
  },
  app: {
    previewFailed: (msg: string) => `预览失败：${msg}`,
  },
  footer: {
    text: 'AutoPatch · Built with LangGraph + React · Open Source',
  },
}

export type Locale = typeof zh
