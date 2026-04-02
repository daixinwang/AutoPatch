/**
 * useTheme.ts
 * -----------
 * 主题管理 Hook，支持三种模式：
 *   - 'dark'   : 强制深色
 *   - 'light'  : 强制浅色
 *   - 'system' : 跟随操作系统 prefers-color-scheme
 *
 * 持久化到 localStorage，刷新后恢复上次选择。
 */

import { useState, useEffect, useCallback } from 'react'

export type ThemeMode = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'autopatch-theme'

/** 读取系统当前是否处于深色模式 */
function getSystemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** 根据模式计算实际应应用的主题（dark / light） */
function resolveTheme(mode: ThemeMode): 'dark' | 'light' {
  if (mode === 'system') return getSystemDark() ? 'dark' : 'light'
  return mode
}

/** 将 dark/light class 写到 <html> 元素上 */
function applyTheme(resolved: 'dark' | 'light') {
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.classList.toggle('light', resolved === 'light')
}

export function useTheme() {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
    return saved ?? 'dark'
  })

  // 计算当前实际主题
  const resolved = resolveTheme(mode)

  // 每当 mode 变化时，立刻更新 <html> class
  useEffect(() => {
    applyTheme(resolveTheme(mode))
  }, [mode])

  // 监听系统主题变化（仅当 mode === 'system' 时生效）
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (mode === 'system') applyTheme(getSystemDark() ? 'dark' : 'light')
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [mode])

  const setMode = useCallback((next: ThemeMode) => {
    localStorage.setItem(STORAGE_KEY, next)
    setModeState(next)
  }, [])

  return { mode, resolved, setMode }
}
