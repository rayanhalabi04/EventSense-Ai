import type { AuditLog } from '../types'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'accent'

const EVENT_LABELS: Record<string, string> = {
  'auth.login_success': 'Login succeeded',
  'auth.login_failed': 'Login failed',
  'auth.logout': 'Logged out',
  'simulator.message_received': 'Message received',
  'telegram.message_received': 'Message received',
  'message.received': 'Message received',
  'message.intent_classified': 'Intent classified',
  'intent.classified': 'Intent classified',
  'message.risk_detected': 'Risk detected',
  'risk.detected': 'Risk detected',
  'rag.query_executed': 'RAG query completed',
  'rag.query_completed': 'RAG query completed',
  rag_query: 'RAG query completed',
  'rag.retrieval_returned_sources': 'RAG source retrieved',
  'rag.no_source_refusal': 'RAG source unavailable',
  'suggested_reply.generated': 'Suggested reply generated',
  'suggested_reply.refused_no_source': 'Suggested reply refused: no source',
  'suggested_reply.approved': 'Staff reply used',
  'suggested_reply.edited': 'Suggested reply edited',
  'suggested_reply.rejected': 'Suggested reply rejected',
  'telegram.reply_sent': 'Staff reply sent via Telegram',
  'telegram.auto_reply_sent': 'Telegram auto-reply sent',
  'telegram.auto_reply_skipped': 'Telegram auto-reply skipped',
  'task.created': 'Task created',
  'task.updated': 'Task updated',
  'task.status_changed': 'Task status changed',
  'agent.task_created': 'Task created',
  'escalation.created': 'Escalation created',
  'agent.escalation_created': 'Escalation created',
  'escalation.updated': 'Escalation updated',
  'escalation.status_changed': 'Escalation status changed',
  'escalation.resolved': 'Escalation resolved',
  'guardrail.refused': 'Guardrail refused unsafe request',
  guardrail_input_blocked: 'Guardrail refused unsafe request',
  guardrail_retrieval_blocked: 'Guardrail blocked retrieved source',
  guardrail_output_blocked: 'Guardrail blocked unsafe reply',
  guardrail_system_prompt_blocked: 'Guardrail blocked prompt injection',
  guardrail_cross_tenant_blocked: 'Guardrail blocked cross-tenant access',
  guardrail_input_redacted: 'Guardrail redacted message',
  guardrail_retrieval_redacted: 'Guardrail redacted retrieved source',
  guardrail_output_redacted: 'Guardrail redacted reply',
  'conversation.status_changed': 'Conversation status changed',
  'conversation.detail_viewed': 'Conversation detail viewed',
  'tenant.cross_tenant_access_blocked': 'Cross-tenant access blocked',
  'agent.decision_created': 'AI agent decision created',
  'agent.skipped': 'AI agent skipped',
  'agent.started': 'AI agent started',
  'agent.tool_planned': 'AI agent tool planned',
  'agent.tool_executed': 'AI agent tool executed',
  'agent.tool_failed': 'AI agent tool failed',
  'agent.completed': 'AI agent completed',
  'agent.suggested_reply_drafted': 'Suggested reply drafted',
  'agent.human_review_required': 'Human review required',
  'document.created': 'Document created',
  'document.updated': 'Document updated',
  'document.archived': 'Document archived',
  'document.chunked_indexed': 'Document indexed for RAG',
}

const RESOURCE_LABELS: Record<string, string> = {
  conversation: 'Conversation',
  message: 'Message',
  rag_query: 'RAG query',
  suggested_reply: 'Suggested reply',
  escalation: 'Escalation',
  task: 'Task',
  document: 'Document',
  guardrail: 'Guardrail',
}

const EVENT_VARIANTS: Array<[RegExp, BadgeVariant]> = [
  [/guardrail|blocked|refused|failed|risk_detected/, 'danger'],
  [/escalation|human_review|required|skipped/, 'warning'],
  [/auto_reply_sent|reply_sent|approved|completed|resolved/, 'success'],
  [/rag|suggested_reply|agent|intent/, 'info'],
  [/task|conversation|document/, 'accent'],
]

function eventType(log: Pick<AuditLog, 'event_type' | 'action'>): string {
  return log.event_type || log.action || ''
}

function titleize(value: string): string {
  const clean = value.replace(/[._-]+/g, ' ').trim()
  if (!clean) return 'Audit event'
  return clean.charAt(0).toUpperCase() + clean.slice(1)
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function numberValue(value: unknown): string | null {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : null
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

export function auditEventLabel(log: Pick<AuditLog, 'event_type' | 'action'>): string {
  const type = eventType(log)
  return EVENT_LABELS[type] ?? titleize(type)
}

export function auditEventVariant(log: Pick<AuditLog, 'event_type' | 'action'>): BadgeVariant {
  const type = eventType(log)
  return EVENT_VARIANTS.find(([pattern]) => pattern.test(type))?.[1] ?? 'neutral'
}

export function auditResourceLabel(resourceType: string | null | undefined): string {
  if (!resourceType) return 'System'
  return RESOURCE_LABELS[resourceType] ?? titleize(resourceType)
}

export function shortId(id: string | null | undefined): string {
  if (!id) return ''
  return id.length <= 12 ? id : `${id.slice(0, 8)}...`
}

export function auditLogSummary(log: AuditLog): string {
  const details = log.details ?? {}
  const parts = [
    stringValue(details.intent_label) && `Intent: ${stringValue(details.intent_label)}`,
    stringValue(details.risk_level) && `Risk: ${stringValue(details.risk_level)}`,
    stringValue(details.reason) && `Reason: ${titleize(stringValue(details.reason) ?? '')}`,
    stringValue(details.refusal_reason) && `Refusal: ${stringValue(details.refusal_reason)}`,
    stringValue(details.status) && `Status: ${titleize(stringValue(details.status) ?? '')}`,
    stringValue(details.old_status) &&
      stringValue(details.new_status) &&
      `Status: ${titleize(stringValue(details.old_status) ?? '')} -> ${titleize(stringValue(details.new_status) ?? '')}`,
    stringValue(details.task_title) && `Task: ${stringValue(details.task_title)}`,
    stringValue(details.title) && `Title: ${stringValue(details.title)}`,
    stringValue(details.escalation_reason) && `Escalation: ${stringValue(details.escalation_reason)}`,
    stringValue(details.query) && `Query: ${stringValue(details.query)}`,
    numberValue(details.source_count) && `Sources: ${numberValue(details.source_count)}`,
  ].filter(Boolean)

  const sourceTitles = stringList(details.source_document_titles)
  if (sourceTitles.length > 0) {
    parts.push(`Source: ${sourceTitles.slice(0, 2).join(', ')}`)
  }

  const conversationId = shortId(stringValue(details.conversation_id))
  const messageId = shortId(stringValue(details.message_id) || stringValue(details.inbound_message_id))
  const suggestedReplyId = shortId(stringValue(details.suggested_reply_id))
  if (conversationId) parts.push(`Conversation ${conversationId}`)
  if (messageId) parts.push(`Message ${messageId}`)
  if (suggestedReplyId) parts.push(`Reply ${suggestedReplyId}`)

  return parts.join(' | ') || 'No additional details recorded.'
}

export function auditLogSearchText(log: AuditLog): string {
  return [
    eventType(log),
    auditEventLabel(log),
    log.resource_type,
    auditResourceLabel(log.resource_type),
    log.resource_id,
    auditLogSummary(log),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}
