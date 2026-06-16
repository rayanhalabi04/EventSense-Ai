// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface User {
  id: string
  email: string
  full_name: string
  role: 'staff' | 'manager' | 'platform_admin'
  tenant_id: string
  is_active: boolean
}

// ── Tenant ────────────────────────────────────────────────────────────────────

export interface Tenant {
  id: string
  name: string
  slug: string
}

// ── Conversations ─────────────────────────────────────────────────────────────

export type ConversationStatus = 'open' | 'resolved' | 'pending' | 'escalated'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type MessageIntent =
  | 'cancellation'
  | 'complaint'
  | 'payment_issue'
  | 'guest_count_change'
  | 'general_inquiry'
  | 'confirmation'
  | 'follow_up'
  | 'unknown'

/** Mirrors backend `ConversationRead` (`GET /api/v1/conversations`). */
export interface Conversation {
  id: string
  tenant_id: string
  client_name: string
  client_contact?: string | null
  source?: string | null
  external_conversation_id?: string | null
  status: ConversationStatus
  created_at: string
  updated_at: string
}

// ── Messages ──────────────────────────────────────────────────────────────────

export type MessageDirection = 'inbound' | 'outbound'
export type MessageStatus = 'unread' | 'read'

/**
 * Mirrors backend `MessageRead` / `ConversationDetailMessage`. The message text
 * lives in `body` (not `content`), the timestamp in `sent_at` (not `created_at`),
 * and the classified intent in `intent_label` (not `intent`). Most fields are
 * nullable and must be rendered defensively.
 */
export interface Message {
  id: string
  tenant_id: string
  conversation_id: string
  direction: MessageDirection
  status: MessageStatus
  body: string
  source?: string | null
  external_message_id?: string | null
  intent_label?: string | null
  intent_confidence?: number | null
  classified_at?: string | null
  risk_level?: RiskLevel | null
  risk_flags?: string[] | null
  risk_reason?: string | null
  risk_detected_at?: string | null
  sender_user_id?: string | null
  sent_at: string
}

export interface CreateMessageRequest {
  body: string
  direction: MessageDirection
}

/** One entry in the conversation detail audit timeline (`audit_timeline`). */
export interface ConversationAuditEvent {
  id: string
  event_type: string
  actor_user_id?: string | null
  resource_type?: string | null
  resource_id?: string | null
  details: Record<string, unknown>
  created_at: string
}

/**
 * Mirrors backend `ConversationDetailResponse`
 * (`GET /api/v1/conversations/{id}/detail`). NOTE: this is NOT the same shape as
 * `Conversation` — the id field is `conversation_id`, status is
 * `conversation_status`, there is no top-level `source`/`message_count`, and the
 * suggested reply is a single nullable object plus a separate `rag_sources` list.
 */
export interface ConversationDetail {
  conversation_id: string
  client_name: string
  client_contact?: string | null
  conversation_status: ConversationStatus
  created_at: string
  updated_at: string
  messages: Message[]
  latest_inbound_message?: Message | null
  latest_intent_label?: string | null
  latest_intent_confidence?: number | null
  latest_classified_at?: string | null
  latest_risk_level?: RiskLevel | null
  latest_risk_flags?: string[] | null
  latest_risk_reason?: string | null
  latest_risk_detected_at?: string | null
  audit_timeline: ConversationAuditEvent[]
  suggested_reply?: SuggestedReply | null
  rag_sources: RagSource[]
  tasks: Task[]
  escalations: Escalation[]
}

// ── Suggested Replies ─────────────────────────────────────────────────────────

export type ReplyStatus = 'draft' | 'approved' | 'edited' | 'rejected'

/** Mirrors backend `SuggestedReplyRead`. The reply text lives in `suggested_text`. */
export interface SuggestedReply {
  id: string
  tenant_id: string
  conversation_id: string
  message_id?: string | null
  suggested_text: string
  status: ReplyStatus
  source_document_ids: string[]
  rag_sources: RagSource[]
  answer_supported: boolean
  refusal_reason?: string | null
  generation_method: string
  /** Set when the reply was delivered to the client automatically (e.g. Telegram). */
  auto_sent_at?: string | null
  sent_channel?: string | null
  created_by_user_id?: string | null
  approved_by_user_id?: string | null
  created_at: string
  updated_at: string
}

/** Mirrors the backend RAG source dict; the human label is `document_title`. */
export interface RagSource {
  document_id: string
  document_title: string
  document_type?: string
  content?: string
  score?: number
  chunk_index?: number
  metadata?: Record<string, unknown>
}

// ── Inbox ─────────────────────────────────────────────────────────────────────

export interface InboxSummary {
  open_count: number
  pending_count: number
  escalated_count: number
  high_risk_count: number
  resolved_today: number
}

export interface InboxFilters {
  status?: ConversationStatus
  source?: string
  direction?: MessageDirection
  page?: number
  page_size?: number
}

/**
 * One row from `GET /api/v1/inbox/messages` — the latest message per
 * conversation. Mirrors the backend `InboxMessageRow` schema. Optional fields
 * may be null/absent and must be rendered defensively.
 */
export interface InboxMessage {
  conversation_id: string
  latest_message_id: string
  client_name: string
  client_contact?: string | null
  message_preview: string
  latest_message_body: string
  latest_message_at: string
  status: ConversationStatus
  source?: string | null
  direction: MessageDirection
  intent_label?: string | null
  intent_confidence?: number | null
  classified_at?: string | null
  risk_level?: RiskLevel | null
  risk_flags?: string[] | null
  risk_reason?: string | null
  risk_detected_at?: string | null
}

// ── Tasks ─────────────────────────────────────────────────────────────────────

export type TaskStatus = 'open' | 'in_progress' | 'completed' | 'cancelled'
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'

/** Mirrors backend `TaskRead`. NOTE: due date is `due_at` (not `due_date`). */
export interface Task {
  id: string
  tenant_id: string
  conversation_id?: string | null
  message_id?: string | null
  title: string
  description?: string | null
  status: TaskStatus
  priority?: TaskPriority
  due_at?: string | null
  assigned_to_user_id?: string | null
  created_by_user_id?: string
  created_at: string
  updated_at: string
}

export interface CreateTaskRequest {
  title: string
  description?: string
  priority?: TaskPriority
  due_date?: string
  conversation_id?: string
}

export interface UpdateTaskRequest {
  status?: TaskStatus
  title?: string
  description?: string
  priority?: TaskPriority
  due_date?: string
}

// ── Escalations ───────────────────────────────────────────────────────────────

export type EscalationStatus = 'open' | 'acknowledged' | 'resolved' | 'dismissed'
export type EscalationSeverity = 'medium' | 'high' | 'critical'

/**
 * Mirrors backend `EscalationRead`. NOTE: there is no `title` or `severity` —
 * use `ai_summary` for a headline and `risk_level` for urgency.
 */
export interface Escalation {
  id: string
  tenant_id: string
  conversation_id?: string | null
  message_id?: string | null
  created_by_user_id?: string
  assigned_manager_user_id?: string | null
  intent_label?: string | null
  risk_level?: RiskLevel | null
  risk_reason?: string | null
  ai_summary?: string | null
  suggested_next_step?: string | null
  status: EscalationStatus
  created_at: string
  updated_at: string
  resolved_at?: string | null
}

export interface UpdateEscalationRequest {
  status?: EscalationStatus
}

// ── Documents ─────────────────────────────────────────────────────────────────

export type DocumentStatus = 'active' | 'archived'
export type DocumentType = 'policy' | 'contract' | 'faq' | 'pricing' | 'template' | 'other'

export interface Document {
  id: string
  tenant_id: string
  title: string
  document_type: DocumentType
  status: DocumentStatus
  content?: string
  created_at: string
  updated_at: string
}

export interface DocumentFilters {
  document_type?: DocumentType
  status?: DocumentStatus
  search?: string
}

// ── Audit Logs ────────────────────────────────────────────────────────────────

export interface AuditLog {
  id: string
  tenant_id: string
  user_id?: string
  action: string
  resource_type?: string
  resource_id?: string
  details?: Record<string, unknown>
  created_at: string
}

// ── Pagination ────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ── Simulator ─────────────────────────────────────────────────────────────────

export interface SimulatorMessage {
  content: string
  client_name?: string
  client_phone?: string
}

export interface SimulatorConversation {
  id: string
  client_name: string
  last_message: string
  risk_level: RiskLevel
  created_at: string
}
