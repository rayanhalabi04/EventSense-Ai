import type { Escalation, Task } from '../types'

const INTENT_LABELS: Record<string, string> = {
  cancellation_request: 'Cancellation request',
  complaint: 'Complaint',
  guest_count_change: 'Guest count change',
  human_escalation: 'Human support',
  payment_issue: 'Payment issue',
  pricing_request: 'Pricing request',
  urgent_change: 'Urgent change',
}

const ESCALATION_TITLES: Record<string, string> = {
  cancellation_request: 'Cancellation request needs manager review',
  complaint: 'Client complaint needs manager review',
  guest_count_change: 'Guest count change needs manager review',
  human_escalation: 'Client requested human support',
  payment_issue: 'Payment issue needs manager review',
  urgent_change: 'Urgent event change needs manager review',
}

const ESCALATION_REASONS: Record<string, string> = {
  cancellation_request: 'Cancellation/refund request requires manager review.',
  complaint: 'Complaint detected in the client message.',
  guest_count_change: 'Guest count change may affect catering, seating, or capacity.',
  human_escalation: 'Client asked for human assistance.',
  payment_issue: 'Payment confirmation requires staff verification.',
  urgent_change: 'Urgent event change requires fast review.',
}

const TASK_TITLES: Record<string, string> = {
  complaint: 'Review client complaint',
  guest_count_change: 'Review guest count change',
  payment_issue: 'Verify payment status',
  urgent_change: 'Review urgent event change',
}

export function humanizeIntentLabel(label?: string | null): string {
  const normalized = normalizeLabel(label)
  if (!normalized) return 'Client message'

  return (
    INTENT_LABELS[normalized] ??
    normalized
      .split('_')
      .filter(Boolean)
      .map((part, index) => (index === 0 ? capitalize(part) : part))
      .join(' ')
  )
}

export function formatRiskLabel(level?: string | null): string {
  const normalized = normalizeLabel(level)
  if (!normalized) return ''
  return `${capitalize(normalized)} risk`
}

export function formatDueDate(dateStr?: string | null, now = new Date()): string {
  if (!dateStr) return ''

  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return ''

  const dueDay = startOfLocalDay(date).getTime()
  const today = startOfLocalDay(now).getTime()
  const tomorrow = today + 86_400_000

  if (dueDay < today) return 'Overdue'
  if (dueDay === today) return 'Due today'
  if (dueDay === tomorrow) return 'Due tomorrow'

  const diff = date.getTime() - now.getTime()
  if (diff > 0 && diff <= 86_400_000) return 'Due within 24h'

  return `Due ${date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
}

export function extractOriginalMessage(description?: string | null): string {
  if (!description) return ''

  const markerMatch = description.match(/Original client message:\s*([\s\S]*)/i)
  const message = markerMatch?.[1]?.trim()
  if (message) return message

  const trimmed = description.trim()
  if (/Created automatically from an inbound message/i.test(trimmed)) return ''
  return trimmed
}

export function formatSourceLabel(source?: string | null): string {
  const normalized = normalizeLabel(source)
  if (!normalized) return ''
  if (normalized === 'telegram') return 'Telegram'
  if (normalized.includes('telegram')) return 'Telegram'
  if (normalized.includes('inbound_auto') || normalized.includes('automated')) return 'Auto-created'
  if (normalized === 'message') return 'Message'
  return humanizeIntentLabel(normalized)
}

export function taskIntent(task: Task): string | null {
  return extractFieldFromTaskDescription(task.description, 'Detected intent')
}

export function taskRisk(task: Task): string | null {
  return extractFieldFromTaskDescription(task.description, 'Risk level')
}

export function formatTaskTitle(task: Task): string {
  const intent = normalizeLabel(taskIntent(task))
  return (intent && TASK_TITLES[intent]) || task.title
}

export function taskSourceLabel(task: Task): string {
  if (task.message_id && isAutoCreatedTask(task)) return 'Auto-created'
  if (task.message_id) return 'Telegram'
  return ''
}

export function taskBadgeLabels(task: Task): string[] {
  const labels: string[] = []
  const source = taskSourceLabel(task)
  const due = formatDueDate(task.due_at)
  const assignee = task.assigned_to_user_id ? '' : 'Unassigned'

  if (source) labels.push(source)
  if (assignee) labels.push(assignee)
  if (due) labels.push(due)

  return labels
}

export function formatEscalationTitle(escalation: Pick<Escalation, 'intent_label' | 'ai_summary'>): string {
  const intent = normalizeLabel(escalation.intent_label) || extractIntentFromEscalationSummary(escalation.ai_summary)
  return (intent && ESCALATION_TITLES[intent]) || 'Client message needs manager review'
}

export function escalationReason(escalation: Pick<Escalation, 'intent_label' | 'risk_reason' | 'suggested_next_step' | 'ai_summary'>): string {
  const intent = normalizeLabel(escalation.intent_label) || extractIntentFromEscalationSummary(escalation.ai_summary)
  if (intent && ESCALATION_REASONS[intent]) return ESCALATION_REASONS[intent]

  const nextStep = escalation.suggested_next_step?.trim()
  if (nextStep && !/Manager review recommended by the (inbound pipeline|focused agent)\./i.test(nextStep)) {
    return nextStep
  }

  return escalation.risk_reason?.trim() || 'Manager review recommended.'
}

export function escalationSource(escalation: Pick<Escalation, 'ai_summary' | 'message_id'>): string {
  const source = escalation.ai_summary?.match(/^Inbound\s+(.+?)\s+classified/i)?.[1]
  const label = formatSourceLabel(source)
  if (label === 'Telegram') return 'Telegram message'
  return label || (escalation.message_id ? 'Telegram message' : 'Client message')
}

export function escalationMeta(escalation: Escalation): string {
  const parts = [
    escalationSource(escalation),
    humanizeIntentLabel(escalation.intent_label),
    formatRiskLabel(escalation.risk_level),
    'Auto-send skipped',
  ].filter(Boolean)

  return parts.join(' · ')
}

function extractIntentFromEscalationSummary(summary?: string | null): string | null {
  return summary?.match(/classified as\s+([a-z_]+)/i)?.[1] ?? null
}

function extractFieldFromTaskDescription(description: string | null | undefined, label: string): string | null {
  if (!description) return null
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return description.match(new RegExp(`${escaped}:\\s*([^\\n]+)`, 'i'))?.[1]?.trim() ?? null
}

function isAutoCreatedTask(task: Task): boolean {
  return /Created automatically from an inbound message/i.test(task.description ?? '')
}

function normalizeLabel(value?: string | null): string {
  return value?.trim().toLowerCase().replace(/\s+/g, '_') ?? ''
}

function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}
