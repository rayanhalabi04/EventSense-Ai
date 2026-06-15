import type { RiskLevel, TaskStatus, EscalationStatus, EscalationSeverity, TaskPriority } from '../../types'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'accent'
  className?: string
}

const VARIANT_CLASSES: Record<NonNullable<BadgeProps['variant']>, string> = {
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  info: 'bg-info-soft text-info',
  neutral: 'bg-surface-high text-text-muted',
  accent: 'bg-accent-soft text-text-accent',
}

const RISK_MAP: Record<RiskLevel, { label: string; variant: BadgeProps['variant'] }> = {
  low: { label: 'Low Risk', variant: 'success' },
  medium: { label: 'Medium', variant: 'warning' },
  high: { label: 'High Risk', variant: 'danger' },
  critical: { label: 'Critical', variant: 'danger' },
}

const TASK_STATUS_MAP: Record<TaskStatus, { label: string; variant: BadgeProps['variant'] }> = {
  open: { label: 'Open', variant: 'info' },
  in_progress: { label: 'In Progress', variant: 'warning' },
  completed: { label: 'Completed', variant: 'success' },
  cancelled: { label: 'Cancelled', variant: 'neutral' },
}

const PRIORITY_MAP: Record<TaskPriority, { label: string; variant: BadgeProps['variant'] }> = {
  low: { label: 'Low', variant: 'neutral' },
  medium: { label: 'Medium', variant: 'info' },
  high: { label: 'High', variant: 'warning' },
  urgent: { label: 'Urgent', variant: 'danger' },
}

const ESCALATION_STATUS_MAP: Record<EscalationStatus, { label: string; variant: BadgeProps['variant'] }> = {
  open: { label: 'Open', variant: 'danger' },
  acknowledged: { label: 'Acknowledged', variant: 'warning' },
  resolved: { label: 'Resolved', variant: 'success' },
  dismissed: { label: 'Dismissed', variant: 'neutral' },
}

const SEVERITY_MAP: Record<EscalationSeverity, { label: string; variant: BadgeProps['variant'] }> = {
  medium: { label: 'Medium', variant: 'warning' },
  high: { label: 'High', variant: 'danger' },
  critical: { label: 'Critical', variant: 'danger' },
}

type BadgeValue = string | null | undefined
type BadgeConfig = { label: string; variant: BadgeProps['variant'] }

const UNKNOWN_BADGE: BadgeConfig = { label: 'Unknown', variant: 'neutral' }

function getBadgeConfig<T extends string>(
  value: BadgeValue,
  map: Record<T, BadgeConfig>,
  fallback: BadgeConfig = UNKNOWN_BADGE,
) {
  if (!value) return fallback

  const normalized = value.toLowerCase() as T
  return map[normalized] ?? fallback
}

export function Badge({ children, variant = 'neutral', className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${VARIANT_CLASSES[variant]} ${className}`}>
      {children}
    </span>
  )
}

export function RiskBadge({ level }: { level?: BadgeValue }) {
  const { label, variant } = getBadgeConfig(level, RISK_MAP)
  return <Badge variant={variant}>{label}</Badge>
}

export function TaskStatusBadge({ status }: { status?: BadgeValue }) {
  const { label, variant } = getBadgeConfig(status, TASK_STATUS_MAP)
  return <Badge variant={variant}>{label}</Badge>
}

export function PriorityBadge({ priority }: { priority?: BadgeValue }) {
  const { label, variant } = getBadgeConfig(priority, PRIORITY_MAP)
  return <Badge variant={variant}>{label}</Badge>
}

export function EscalationStatusBadge({ status }: { status?: BadgeValue }) {
  const { label, variant } = getBadgeConfig(status, ESCALATION_STATUS_MAP)
  return <Badge variant={variant}>{label}</Badge>
}

export function SeverityBadge({ severity }: { severity?: BadgeValue }) {
  const { label, variant } = getBadgeConfig(severity, SEVERITY_MAP)
  return <Badge variant={variant}>{label}</Badge>
}
