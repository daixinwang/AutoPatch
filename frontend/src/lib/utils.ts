import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** 合并 Tailwind 类名，解决冲突 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** 格式化耗时为可读字符串 */
export function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(0)
  return `${m}m ${s}s`
}

/** 生成当前时间戳字符串 HH:MM:SS */
export function timestamp(): string {
  return new Date().toLocaleTimeString('en-US', { hour12: false })
}

/** 从 diff 文本中提取变更文件列表 */
export function extractChangedFiles(diff: string): string[] {
  const matches = diff.match(/^diff --git a\/(.+?) b\//gm) ?? []
  return matches.map(m => m.replace(/^diff --git a\//, '').replace(/ b\/.*$/, ''))
}

/** 统计 diff 的增删行数 */
export function countDiffLines(diff: string): { added: number; removed: number } {
  const lines = diff.split('\n')
  let added = 0
  let removed = 0
  for (const line of lines) {
    if (line.startsWith('+') && !line.startsWith('+++')) added++
    if (line.startsWith('-') && !line.startsWith('---')) removed++
  }
  return { added, removed }
}
