import { describe, expect, it } from 'vitest'
import type { Escalation, Task } from '../types'
import {
  extractOriginalMessage,
  formatDueDate,
  formatEscalationTitle,
  humanizeIntentLabel,
  taskBadgeLabels,
} from './workflowDisplay'

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    tenant_id: 'tenant-1',
    conversation_id: 'conversation-1',
    message_id: 'message-1',
    title: 'Review client complaint',
    description: [
      'Created automatically from an inbound message.',
      '',
      'Detected intent: complaint',
      'Risk level: high',
      '',
      'Original client message:',
      'I am very upset. The decoration sample is not what we agreed on.',
    ].join('\n'),
    status: 'open',
    due_at: '2026-06-17T18:00:00Z',
    assigned_to_user_id: 'user-1',
    created_by_user_id: 'user-1',
    created_at: '2026-06-16T18:00:00Z',
    updated_at: '2026-06-16T18:00:00Z',
    ...overrides,
  }
}

function makeEscalation(overrides: Partial<Escalation> = {}): Escalation {
  return {
    id: 'escalation-1',
    tenant_id: 'tenant-1',
    conversation_id: 'conversation-1',
    message_id: 'message-1',
    created_by_user_id: undefined,
    assigned_manager_user_id: null,
    intent_label: 'payment_issue',
    risk_level: 'medium',
    risk_reason: null,
    ai_summary: 'Inbound telegram classified as payment_issue (risk: medium) was not auto-sent and needs manager review.',
    suggested_next_step: 'Manager review recommended by the inbound pipeline.',
    status: 'open',
    created_at: '2026-06-16T18:00:00Z',
    updated_at: '2026-06-16T18:00:00Z',
    resolved_at: null,
    ...overrides,
  }
}

describe('workflow display formatting', () => {
  it('humanizes snake_case intent labels', () => {
    expect(humanizeIntentLabel('guest_count_change')).toBe('Guest count change')
    expect(humanizeIntentLabel('payment_issue')).toBe('Payment issue')
    expect(humanizeIntentLabel('pricing_request')).toBe('Pricing request')
  })

  it('formats task due dates without just-now language', () => {
    const now = new Date('2026-06-17T10:00:00')

    expect(formatDueDate('2026-06-17T10:01:00', now)).toBe('Due today')
    expect(formatDueDate('2026-06-18T09:00:00', now)).toBe('Due tomorrow')
    expect(formatDueDate('2026-06-16T23:59:00', now)).toBe('Overdue')
  })

  it('returns manager-friendly escalation titles', () => {
    expect(formatEscalationTitle(makeEscalation({ intent_label: 'complaint' }))).toBe(
      'Client complaint needs manager review',
    )
    expect(formatEscalationTitle(makeEscalation({ intent_label: 'urgent_change' }))).toBe(
      'Urgent event change needs manager review',
    )
    expect(formatEscalationTitle(makeEscalation({ intent_label: null, ai_summary: null }))).toBe(
      'Client message needs manager review',
    )
  })

  it('extracts the original message from automated task descriptions', () => {
    expect(extractOriginalMessage(makeTask().description)).toBe(
      'I am very upset. The decoration sample is not what we agreed on.',
    )
  })

  it('does not create an Unknown badge when task data is missing', () => {
    expect(taskBadgeLabels(makeTask({ assigned_to_user_id: null, due_at: null, message_id: null }))).toEqual([
      'Unassigned',
    ])
  })
})
