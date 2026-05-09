import type { Locale } from './zh'

export const en: Locale = {
  sidebar: {
    newFix:   'New Fix',
    noHistory: 'No history yet',
    collapse:  'Collapse sidebar',
    expand:    'Expand sidebar',
    relativeTime(ts: number): string {
      const diff = Date.now() - ts
      const m = Math.floor(diff / 60_000)
      if (m < 1)  return 'just now'
      if (m < 60) return `${m}m ago`
      const h = Math.floor(m / 60)
      if (h < 24) return `${h}h ago`
      return `${Math.floor(h / 24)}d ago`
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
    previewBtn:      'Preview',
    resetBtn:        'Reset',
    cancelBtn:       'Cancel',
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
    prError:      (msg: string) => `Failed to create PR: ${msg}`,
  },
  issue: {
    open:         'Open',
    closed:       'Closed',
    noBody:       '(No description)',
    comments:     (n: number) => `${n} comment${n === 1 ? '' : 's'}`,
    viewOnGitHub: 'View on GitHub',
    confirmStart: 'Confirm & Start Auto-Fix',
  },
  app: {
    previewFailed: (msg: string) => `Preview failed: ${msg}`,
  },
  footer: {
    text: 'AutoPatch · Built with LangGraph + React · Open Source',
  },
}
