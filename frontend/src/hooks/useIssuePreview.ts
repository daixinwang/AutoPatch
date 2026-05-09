import { useState, useCallback } from 'react'
import type { IssuePreview, PatchInput } from '../types'

export type PreviewStatus = 'idle' | 'loading' | 'success' | 'error'

export function useIssuePreview() {
  const [previewStatus, setPreviewStatus] = useState<PreviewStatus>('idle')
  const [preview, setPreview]             = useState<IssuePreview | null>(null)
  const [previewError, setPreviewError]   = useState<string | null>(null)

  const fetchPreview = useCallback(async (input: PatchInput) => {
    setPreviewStatus('loading')
    setPreviewError(null)
    setPreview(null)

    try {
      const res = await fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repoUrl:     input.repoUrl,
          issueNumber: Number(input.issueNumber),
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(data.detail || `Error ${res.status}`)
      }
      const data: IssuePreview = await res.json()
      setPreview(data)
      setPreviewStatus('success')
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : String(err))
      setPreviewStatus('error')
    }
  }, [])

  const clearPreview = useCallback(() => {
    setPreviewStatus('idle')
    setPreview(null)
    setPreviewError(null)
  }, [])

  return { previewStatus, preview, previewError, fetchPreview, clearPreview }
}
