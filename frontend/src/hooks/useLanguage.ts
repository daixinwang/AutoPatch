import { useState, useCallback } from 'react'

export type Lang = 'zh' | 'en'

const STORAGE_KEY = 'autopatch_lang'

function detectDefault(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'zh' || stored === 'en') return stored
  return navigator.language.startsWith('zh') ? 'zh' : 'en'
}

export function useLanguage() {
  const [lang, setLangState] = useState<Lang>(detectDefault)

  const setLang = useCallback((next: Lang) => {
    localStorage.setItem(STORAGE_KEY, next)
    setLangState(next)
  }, [])

  return { lang, setLang }
}
