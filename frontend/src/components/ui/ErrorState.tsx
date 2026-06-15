import { AlertCircle } from 'lucide-react'

interface Props {
  message?: string
  onRetry?: () => void
}

export function ErrorState({ message = 'Something went wrong.', onRetry }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-14 h-14 rounded-xl bg-danger-soft border border-danger/20 flex items-center justify-center mb-4">
        <AlertCircle className="w-6 h-6 text-danger" />
      </div>
      <p className="text-sm text-text-muted mb-4">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary text-sm">
          Try again
        </button>
      )}
    </div>
  )
}
