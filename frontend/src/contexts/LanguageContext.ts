import { createContext, useContext } from 'react'
import { zh } from '../i18n/zh'
import type { Locale } from '../i18n/zh'

export const LanguageContext = createContext<Locale>(zh)

export function useT(): Locale {
  return useContext(LanguageContext)
}
