/**
 * Build a short, developer-facing diagnostic string from a failed API call so
 * the UI can show the real HTTP status/detail (e.g. "HTTP 500 — ...") instead of
 * only a generic "Could not load" message. Returns `undefined` when there is
 * nothing useful to show.
 *
 * Shape-tolerant on purpose: React Query hands back an unknown error, which is
 * usually an AxiosError but may be a plain Error.
 */
export function apiErrorDetail(error: unknown): string | undefined {
  if (!error) return undefined
  const err = error as {
    response?: { status?: number; data?: { detail?: unknown } }
    message?: string
  }
  const status = err.response?.status
  const rawDetail = err.response?.data?.detail
  const detail =
    typeof rawDetail === 'string'
      ? rawDetail
      : rawDetail != null
        ? JSON.stringify(rawDetail)
        : undefined

  const parts = [status != null ? `HTTP ${status}` : undefined, detail].filter(
    Boolean,
  )
  if (parts.length > 0) return parts.join(' — ')
  return err.message || undefined
}
