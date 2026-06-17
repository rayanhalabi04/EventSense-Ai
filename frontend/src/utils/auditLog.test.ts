import { describe, expect, it } from 'vitest'
import type { AuditLog } from '../types'
import {
  auditEventLabel,
  auditLogSearchText,
  auditLogSummary,
  auditResourceLabel,
  shortId,
} from './auditLog'

function makeLog(overrides: Partial<AuditLog> = {}): AuditLog {
  return {
    id: 'audit-1',
    tenant_id: 'tenant-1',
    actor_user_id: null,
    event_type: 'message.intent_classified',
    resource_type: 'message',
    resource_id: '12345678-1234-1234-1234-123456789abc',
    details: {},
    created_at: '2026-06-15T10:00:00Z',
    ...overrides,
  }
}

describe('audit log formatting', () => {
  it('maps backend event_type values to readable labels', () => {
    expect(auditEventLabel(makeLog({ event_type: 'message.intent_classified' }))).toBe('Intent classified')
    expect(auditEventLabel(makeLog({ event_type: 'telegram.auto_reply_skipped' }))).toBe(
      'Telegram auto-reply skipped',
    )
    expect(auditEventLabel(makeLog({ event_type: 'guardrail_system_prompt_blocked' }))).toBe(
      'Guardrail blocked prompt injection',
    )
  })

  it('falls back to legacy action when event_type is missing', () => {
    expect(auditEventLabel(makeLog({ event_type: '', action: 'rag_query' }))).toBe('RAG query completed')
  })

  it('summarizes useful detail fields', () => {
    const summary = auditLogSummary(
      makeLog({
        event_type: 'telegram.auto_reply_skipped',
        details: {
          intent_label: 'pricing',
          risk_level: 'low',
          reason: 'no_rag_source',
          conversation_id: 'abcdef12-9999-8888-7777-666666666666',
          message_id: '12345678-9999-8888-7777-666666666666',
        },
      }),
    )

    expect(summary).toContain('Intent: pricing')
    expect(summary).toContain('Risk: low')
    expect(summary).toContain('Reason: No rag source')
    expect(summary).toContain('Conversation abcdef12...')
    expect(summary).toContain('Message 12345678...')
  })

  it('formats resource names and short IDs', () => {
    expect(auditResourceLabel('suggested_reply')).toBe('Suggested reply')
    expect(shortId('12345678-1234-1234-1234-123456789abc')).toBe('12345678...')
  })

  it('includes details in search text', () => {
    const text = auditLogSearchText(
      makeLog({
        event_type: 'suggested_reply.generated',
        details: { source_document_titles: ['pricing-packages.txt'] },
      }),
    )

    expect(text).toContain('suggested reply generated')
    expect(text).toContain('pricing-packages.txt')
  })
})
