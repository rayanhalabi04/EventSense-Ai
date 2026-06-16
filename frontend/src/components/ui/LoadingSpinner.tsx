interface Props {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const SIZES: Record<NonNullable<Props['size']>, string> = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-10 w-10',
}

function LoadingSpinner({ size = 'md', className = '' }: Props) {
  return (
    <div
      className={`${SIZES[size]} animate-spin rounded-full border-2 border-border border-t-accent ${className}`}
      aria-label="Loading"
    />
  )
}

export function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[300px]">
      <LoadingSpinner size="lg" />
    </div>
  )
}
