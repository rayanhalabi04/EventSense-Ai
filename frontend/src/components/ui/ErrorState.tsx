import { AlertCircle } from 'lucide-react'

interface Props {
  message?: string
  onRetry?: () => void
  /** Extra diagnostic line (e.g. "HTTP 500 — ...") shown for debugging. */
  detail?: string
}

export function ErrorState({ message = 'Something went wrong.', onRetry, detail }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-14 h-14 rounded-xl bg-danger-soft border border-danger/20 flex items-center justify-center mb-4">
        <AlertCircle className="w-6 h-6 text-danger" />
      </div>
      <p className="text-sm text-text-muted mb-1">{message}</p>
      {detail && (
        <p className="text-xs text-danger/80 font-mono mb-4 max-w-md break-words">{detail}</p>
      )}
      {!detail && <div className="mb-4" />}
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary text-sm">
          Try again
        </button>
      )}
    </div>
  )
}
