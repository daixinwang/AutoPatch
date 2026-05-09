import { useState, useCallback } from 'react'
import type { HistoryRecord } from '../types'

const STORAGE_KEY = 'autopatch_history'
const MAX_RECORDS = 50

function loadRecords(): HistoryRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as HistoryRecord[]) : []
  } catch {
    return []
  }
}

function saveRecords(records: HistoryRecord[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
}

export function useHistory() {
  const [records, setRecords] = useState<HistoryRecord[]>(loadRecords)

  const addRecord = useCallback((record: HistoryRecord) => {
    setRecords(prev => {
      const next = [record, ...prev].slice(0, MAX_RECORDS)
      saveRecords(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setRecords([])
  }, [])

  return { records, addRecord, clearAll }
}
