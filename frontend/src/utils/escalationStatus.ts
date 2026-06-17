import type { EscalationStatus } from '../types'

export const ESCALATION_FILTER_TABS: { label: string; value: EscalationStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Open', value: 'open' },
  { label: 'Acknowledged', value: 'in_review' },
  { label: 'Resolved', value: 'resolved' },
]

export const ESCALATION_STATUS_OPTIONS: { label: string; value: EscalationStatus }[] = [
  { label: 'Open', value: 'open' },
  { label: 'Acknowledged', value: 'in_review' },
  { label: 'Resolved', value: 'resolved' },
]

export const ESCALATION_STATUS_LABELS: Record<EscalationStatus, string> = {
  open: 'Open',
  in_review: 'Acknowledged',
  resolved: 'Resolved',
  cancelled: 'Cancelled',
}

export function getEscalationStatusLabel(status?: string | null): string {
  if (!status) return 'Unknown'
  const normalized = status.toLowerCase() as EscalationStatus
  return ESCALATION_STATUS_LABELS[normalized] ?? 'Unknown'
}
