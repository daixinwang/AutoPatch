export const zh = {
  sidebar: {
    newFix:   '新建修复',
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
    agentWorking:    '修复中...',
    startBtn:        '开始修复',
    previewBtn:      '预览',
    resetBtn:        '重置',
    cancelBtn:       '取消',
  },
  terminal: {
    shellTitle: 'autopatch — bash',
    waiting:    '等待任务输入...',
    linesUnit:  '行',
  },
  result: {
    successTitle: '补丁生成成功',
    failTitle:    '审核未通过',
    added:        '新增',
    removed:      '删除',
    steps:        '步骤',
    time:         '耗时',
    changed:      '变更文件：',
    viewPR:       '查看 PR',
    createPR:     '创建 PR',
    creating:     '创建中...',
    copied:       '已复制！',
    copyDiff:     '复制 Diff',
    applyPatch:   '应用补丁：',
    prError:      (msg: string) => `PR 创建失败：${msg}`,
  },
  issue: {
    open:         '开放',
    closed:       '已关闭',
    noBody:       '（暂无正文）',
    comments:     (n: number) => `${n} 条评论`,
    viewOnGitHub: '在 GitHub 查看',
    confirmStart: '确认并开始修复',
  },
  app: {
    previewFailed: (msg: string) => `预览失败：${msg}`,
  },
  footer: {
    text: 'AutoPatch · Built with LangGraph + React · Open Source',
  },
}

export type Locale = typeof zh
