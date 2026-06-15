/**
 * TypeScript mirrors of the EventSense AI backend schemas.
 * Kept intentionally close to the Pydantic models so the API contract is explicit.
 */

export type UUID = string;
export type ISODateTime = string;

export type UserRole = "staff" | "manager" | "platform_admin";
export type ConversationStatus = "open" | "closed" | "escalated";
export type MessageDirection = "inbound" | "outbound";
export type MessageStatus = "unread" | "read";
export type TaskStatus = "open" | "in_progress" | "completed" | "cancelled";
export type EscalationStatus = "open" | "in_review" | "resolved" | "cancelled";
export type SuggestedReplyStatus = "draft" | "approved" | "edited" | "rejected";
export type DocumentStatus = "active" | "archived";
export type DocumentType =
  | "pricing"
  | "package"
  | "faq"
  | "deposit_policy"
  | "cancellation_policy"
  | "contract_terms"
  | "service_description"
  | "decoration_rules"
  | "catering_rules"
  | "other";
export type RiskLevel = "low" | "medium" | "high" | string;

export interface AuthUser {
  id: UUID;
  email: string;
  full_name: string;
  role: UserRole;
  tenant_id: UUID;
  is_active: boolean;
}

export interface Tenant {
  id: UUID;
  name: string;
  slug: string;
  kind: "customer" | "platform";
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface InboxSummary {
  total_open: number;
  unread_or_new: number;
  high_risk: number;
}

export interface InboxItem {
  conversation_id: UUID;
  latest_message_id: UUID | null;
  client_name: string;
  client_contact: string | null;
  latest_message_preview: string | null;
  latest_message_at: ISODateTime | null;
  latest_message_direction: MessageDirection | null;
  intent_label: string | null;
  intent_confidence: number | null;
  classified_at: ISODateTime | null;
  risk_level: RiskLevel | null;
  risk_flags: string[] | null;
  risk_reason: string | null;
  risk_detected_at: ISODateTime | null;
  unread_count: number;
  has_unread: boolean;
  conversation_status: ConversationStatus;
  updated_at: ISODateTime;
}

export interface InboxResponse {
  items: InboxItem[];
  total: number;
  total_unread: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ConversationItem {
  id: UUID;
  tenant_id: UUID;
  client_name: string;
  client_contact: string | null;
  status: ConversationStatus;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ConversationMessage {
  id: UUID;
  tenant_id: UUID;
  conversation_id: UUID;
  direction: MessageDirection;
  status: MessageStatus;
  body: string;
  source: string | null;
  intent_label: string | null;
  intent_confidence: number | null;
  classified_at: ISODateTime | null;
  risk_level: RiskLevel | null;
  risk_flags: string[] | null;
  risk_reason: string | null;
  risk_detected_at: ISODateTime | null;
  sender_user_id: UUID | null;
  sent_at: ISODateTime;
}

export interface AuditEvent {
  id: UUID;
  event_type: string;
  actor_user_id: UUID | null;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: ISODateTime;
}

export interface RagSource {
  document_id: UUID;
  document_title: string;
  document_type: string;
  content: string;
  score: number;
  [key: string]: unknown;
}

export interface SuggestedReply {
  id: UUID;
  tenant_id: UUID;
  conversation_id: UUID;
  message_id: UUID | null;
  suggested_text: string;
  status: SuggestedReplyStatus;
  source_document_ids: string[];
  rag_sources: RagSource[];
  answer_supported: boolean;
  refusal_reason: string | null;
  generation_method: string;
  created_by_user_id: UUID | null;
  approved_by_user_id: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Task {
  id: UUID;
  tenant_id: UUID;
  conversation_id: UUID;
  message_id: UUID | null;
  title: string;
  description: string | null;
  assigned_to_user_id: UUID | null;
  due_at: ISODateTime | null;
  status: TaskStatus;
  created_by_user_id: UUID;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Escalation {
  id: UUID;
  tenant_id: UUID;
  conversation_id: UUID;
  message_id: UUID | null;
  created_by_user_id: UUID;
  assigned_manager_user_id: UUID | null;
  intent_label: string | null;
  risk_level: RiskLevel | null;
  risk_reason: string | null;
  ai_summary: string | null;
  suggested_next_step: string | null;
  status: EscalationStatus;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  resolved_at: ISODateTime | null;
}

export interface ConversationDetail {
  conversation_id: UUID;
  client_name: string;
  client_contact: string | null;
  conversation_status: ConversationStatus;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  messages: ConversationMessage[];
  latest_inbound_message: ConversationMessage | null;
  latest_intent_label: string | null;
  latest_intent_confidence: number | null;
  latest_classified_at: ISODateTime | null;
  latest_risk_level: RiskLevel | null;
  latest_risk_flags: string[] | null;
  latest_risk_reason: string | null;
  latest_risk_detected_at: ISODateTime | null;
  audit_timeline: AuditEvent[];
  suggested_reply: SuggestedReply | null;
  rag_sources: RagSource[];
  tasks: Task[];
  escalations: Escalation[];
}

export interface DocumentItem {
  id: UUID;
  tenant_id: UUID;
  title: string;
  document_type: DocumentType;
  original_filename: string | null;
  content_text: string;
  status: DocumentStatus;
  uploaded_by_user_id: UUID;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AuditLog {
  id: UUID;
  tenant_id: UUID;
  actor_user_id: UUID | null;
  event_type: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: ISODateTime;
}

export interface SimulatorMessageResponse {
  message_id: UUID;
  conversation_id: UUID;
  is_new_conversation: boolean;
  conversation_status: string;
  tenant_id: UUID;
  intent_label: string | null;
  intent_confidence: number | null;
  classified_at: ISODateTime | null;
  risk_level: RiskLevel | null;
  risk_flags: string[] | null;
  risk_reason: string | null;
  risk_detected_at: ISODateTime | null;
}

/** Dry-run focused-agent recommendation. Read-only: creates nothing. */
export interface AgentRecommendedTask {
  should_create: boolean;
  reason: string | null;
}

export interface AgentRecommendedEscalation {
  should_escalate: boolean;
  reason: string | null;
}

/** Ids of records the agent created when applied. Null when not recommended or not applied. */
export interface AgentApplied {
  task_id: UUID | null;
  escalation_id: UUID | null;
  suggested_reply_id: UUID | null;
}

export interface AgentToolTrace {
  tool_name: string;
  status: string;
  mode: "dry_run" | "apply" | string;
  summary: string;
  input_summary: string | null;
  output_summary: string | null;
  source_ids: string[];
  suggested_reply_preview: string | null;
  created_id: UUID | null;
  recommended: Record<string, unknown> | null;
}

export interface AgentDecision {
  ran: boolean;
  skipped_reason: string | null;
  message_id: UUID | null;
  conversation_id: UUID | null;
  intent_label: string | null;
  trigger_intent: string | null;
  risk_level: RiskLevel | null;
  risk_reason: string | null;
  recommended_task: AgentRecommendedTask;
  recommended_escalation: AgentRecommendedEscalation;
  human_review_required: boolean;
  confidence: string;
  audit_run_id: UUID;
  tools_used: AgentToolTrace[];
  /** Present only on an apply=true response; null for read-only analysis. */
  applied: AgentApplied | null;
}
