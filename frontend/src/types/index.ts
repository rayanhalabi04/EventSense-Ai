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

export interface Conversation {
  id: string
  tenant_id: string
  client_name: string
  client_phone?: string
  source: string
  status: ConversationStatus
  risk_level: RiskLevel
  last_message_at: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
  tasks: Task[]
  escalations: Escalation[]
  suggested_replies: SuggestedReply[]
  audit_events?: AuditLog[]
}

// ── Messages ──────────────────────────────────────────────────────────────────

export type MessageDirection = 'inbound' | 'outbound'

export interface Message {
  id: string
  conversation_id: string
  content: string
  direction: MessageDirection
  intent?: MessageIntent
  risk_level?: RiskLevel
  created_at: string
  sender_name?: string
}

export interface CreateMessageRequest {
  content: string
  direction: MessageDirection
}

// ── Suggested Replies ─────────────────────────────────────────────────────────

export type ReplyStatus = 'pending' | 'accepted' | 'rejected' | 'edited'

export interface SuggestedReply {
  id: string
  conversation_id: string
  content: string
  status: ReplyStatus
  rag_sources?: RagSource[]
  created_at: string
}

export interface RagSource {
  document_id: string
  title: string
  excerpt: string
  score: number
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

export interface Task {
  id: string
  tenant_id: string
  conversation_id?: string
  title: string
  description?: string
  status: TaskStatus
  priority: TaskPriority
  due_date?: string
  assigned_to_user_id?: string
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

export interface Escalation {
  id: string
  tenant_id: string
  conversation_id?: string
  title: string
  description?: string
  status: EscalationStatus
  severity: EscalationSeverity
  assigned_manager_user_id?: string
  created_at: string
  updated_at: string
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
