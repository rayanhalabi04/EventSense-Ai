import { api } from "@/lib/api";
import type {
  AgentDecision,
  AuditLog,
  ConversationDetail,
  ConversationItem,
  ConversationStatus,
  DocumentItem,
  DocumentType,
  Escalation,
  EscalationStatus,
  InboxResponse,
  InboxSummary,
  SimulatorMessageResponse,
  SuggestedReply,
  SuggestedReplyStatus,
  Task,
  TaskStatus,
  Tenant,
} from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const queryKeys = {
  tenant: ["tenant", "me"] as const,
  inboxSummary: ["inbox", "summary"] as const,
  inbox: (params: string) => ["inbox", params] as const,
  conversation: (id: string) => ["conversation", id] as const,
  documents: (params: string) => ["documents", params] as const,
  tasks: (params: string) => ["tasks", params] as const,
  escalations: (params: string) => ["escalations", params] as const,
  auditLogs: ["audit-logs"] as const,
};

function qs(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}

export function useTenant() {
  return useQuery({
    queryKey: queryKeys.tenant,
    queryFn: () => api.get<Tenant>("/api/v1/tenants/me"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useInboxSummary() {
  return useQuery({
    queryKey: queryKeys.inboxSummary,
    queryFn: () => api.get<InboxSummary>("/api/v1/inbox/summary"),
  });
}

interface InboxParams {
  status?: string;
  search?: string;
  unread_only?: boolean;
  page?: number;
  page_size?: number;
}

export function useInbox(params: InboxParams) {
  const query = qs({
    status: params.status,
    search: params.search,
    unread_only: params.unread_only ? "true" : undefined,
    page: params.page ? String(params.page) : undefined,
    page_size: params.page_size ? String(params.page_size) : undefined,
  });
  return useQuery({
    queryKey: queryKeys.inbox(query),
    queryFn: () => api.get<InboxResponse>(`/api/v1/inbox${query}`),
  });
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.conversation(id ?? ""),
    queryFn: () => api.get<ConversationDetail>(`/api/v1/conversations/${id}/detail`),
    enabled: Boolean(id),
  });
}

export function useDocuments(params: { document_type?: string; status?: string; search?: string }) {
  const query = qs(params);
  return useQuery({
    queryKey: queryKeys.documents(query),
    queryFn: () => api.get<DocumentItem[]>(`/api/v1/documents${query}`),
  });
}

export function useTasks(params: { status?: string } = {}) {
  const query = qs(params);
  return useQuery({
    queryKey: queryKeys.tasks(query),
    queryFn: () => api.get<Task[]>(`/api/v1/tasks${query}`),
  });
}

export function useEscalations(params: { status?: string } = {}) {
  const query = qs(params);
  return useQuery({
    queryKey: queryKeys.escalations(query),
    queryFn: () => api.get<Escalation[]>(`/api/v1/escalations${query}`),
  });
}

export function useAuditLogs(limit = 200) {
  return useQuery({
    queryKey: queryKeys.auditLogs,
    queryFn: () => api.get<AuditLog[]>(`/api/v1/audit-logs?limit=${limit}`),
  });
}

/* ----------------------------- Mutations ----------------------------- */

function useInvalidateConversation(conversationId: string) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) });
    void client.invalidateQueries({ queryKey: ["inbox"] });
  };
}

export function useGenerateReply(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (messageId?: string) =>
      api.post<SuggestedReply>(
        `/api/v1/conversations/${conversationId}/suggested-reply`,
        messageId ? { message_id: messageId } : undefined,
      ),
    onSuccess: invalidate,
  });
}

/**
 * Run the dry-run focused agent for a message. This is read-only: the endpoint
 * accepts `apply=false` only and creates no tasks or escalations, so there is
 * nothing to invalidate. The recommendation is returned and displayed as-is.
 */
export function useRunAgentAnalysis(conversationId: string) {
  return useMutation({
    mutationFn: (messageId: string) =>
      api.post<AgentDecision>(`/api/v1/conversations/${conversationId}/agent/run`, {
        message_id: messageId,
        apply: false,
      }),
  });
}

/**
 * Apply an agent recommendation. Calls the same endpoint with `apply=true`,
 * which creates (or reuses) the recommended task and/or escalation server-side.
 * It still sends no client message and approves/sends no reply. On success the
 * conversation, tasks, escalations, and inbox views are refreshed so the newly
 * created records appear.
 */
export function useApplyAgentRecommendation(conversationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      api.post<AgentDecision>(`/api/v1/conversations/${conversationId}/agent/run`, {
        message_id: messageId,
        apply: true,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) });
      void client.invalidateQueries({ queryKey: ["tasks"] });
      void client.invalidateQueries({ queryKey: ["escalations"] });
      void client.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}

export function useUpdateReply(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: ({
      replyId,
      status,
      suggested_text,
    }: {
      replyId: string;
      status?: SuggestedReplyStatus;
      suggested_text?: string;
    }) =>
      api.patch<SuggestedReply>(`/api/v1/suggested-replies/${replyId}`, { status, suggested_text }),
    onSuccess: invalidate,
  });
}

export function useUpdateConversation(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: ({ status }: { status: ConversationStatus }) =>
      api.patch<ConversationItem>(`/api/v1/conversations/${conversationId}`, { status }),
    onSuccess: invalidate,
  });
}

interface CreateTaskInput {
  conversation_id: string;
  message_id?: string | null;
  title: string;
  description?: string | null;
  due_at?: string | null;
}

export function useCreateTask(conversationId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateTaskInput) => api.post<Task>("/api/v1/tasks", input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["tasks"] });
      if (conversationId) {
        void client.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) });
      }
    },
  });
}

export function useUpdateTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: TaskStatus }) =>
      api.patch<Task>(`/api/v1/tasks/${taskId}`, { status }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

interface CreateEscalationInput {
  conversation_id: string;
  message_id?: string | null;
  ai_summary?: string | null;
  suggested_next_step?: string | null;
}

export function useCreateEscalation(conversationId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateEscalationInput) =>
      api.post<Escalation>("/api/v1/escalations", input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["escalations"] });
      void client.invalidateQueries({ queryKey: ["inbox"] });
      if (conversationId) {
        void client.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) });
      }
    },
  });
}

export function useUpdateEscalation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ escalationId, status }: { escalationId: string; status: EscalationStatus }) =>
      api.patch<Escalation>(`/api/v1/escalations/${escalationId}`, { status }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["escalations"] });
    },
  });
}

interface UploadDocumentInput {
  file: File;
  document_type: DocumentType;
  title?: string;
}

export function useUploadDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, document_type, title }: UploadDocumentInput) => {
      const form = new FormData();
      form.append("file", file);
      form.append("document_type", document_type);
      if (title) form.append("title", title);
      return api.postForm<DocumentItem>("/api/v1/documents/upload", form);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useArchiveDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.del<DocumentItem>(`/api/v1/documents/${documentId}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

interface SimulatorMessageInput {
  client_name?: string;
  client_contact?: string;
  body: string;
  conversation_id?: string;
}

export function useSimulateMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: SimulatorMessageInput) =>
      api.post<SimulatorMessageResponse>("/api/v1/simulator/messages", input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}
