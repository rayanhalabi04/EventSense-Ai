# API Contracts: Message Detail Page

**Branch**: `005-message-detail-page` | **Phase**: 1 — Design

---

## GET /api/v1/conversations/{conversation_id}

Returns the full detail of a single tenant-scoped conversation: header info plus the complete message thread in chronological order. **Side effect**: marks all unread inbound messages in the conversation as read.

**Auth**: Bearer token; requires `staff` or `manager` role.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `conversation_id` | UUID | The conversation to retrieve. Must be a valid UUID (422 otherwise). |

**Query Parameters**: none. Any `tenant_id` supplied as a query parameter is ignored — tenancy is derived from the JWT only (SR-01).

**Response 200**:
```json
{
  "conversation_id": "a0b1c2d3-0000-0000-0000-000000000011",
  "client_name": "Alice Johnson",
  "client_contact": "+44 7700 900123",
  "conversation_status": "open",
  "created_at": "2026-06-03T09:00:00Z",
  "updated_at": "2026-06-03T10:05:00Z",
  "messages": [
    {
      "id": "b1000000-0000-0000-0000-000000000001",
      "body": "Hi, can you send me your wedding package prices?",
      "sent_at": "2026-06-03T09:00:00Z",
      "direction": "inbound",
      "status": "read"
    },
    {
      "id": "b1000000-0000-0000-0000-000000000002",
      "body": "Of course! Our packages start at £4,500. I'll email the full brochure.",
      "sent_at": "2026-06-03T09:30:00Z",
      "direction": "outbound",
      "status": "read"
    }
  ],
  "ai_placeholders": {
    "intent":          { "available": false, "label": "AI Intent" },
    "risk":            { "available": false, "label": "Risk / Sentiment" },
    "rag_sources":     { "available": false, "label": "Knowledge Sources" },
    "suggested_reply": { "available": false, "label": "Suggested Reply" },
    "task_creation":   { "available": false, "label": "Create Task" },
    "escalation":      { "available": false, "label": "Escalate" }
  }
}
```

**Conversation with no messages**:
```json
{
  "conversation_id": "a0b1c2d3-0000-0000-0000-000000000099",
  "client_name": "Empty Client",
  "client_contact": null,
  "conversation_status": "open",
  "created_at": "2026-06-03T08:00:00Z",
  "updated_at": "2026-06-03T08:00:00Z",
  "messages": [],
  "ai_placeholders": { "...": "(same six placeholders as above)" }
}
```

**Failure responses**:

| Status | Condition | `error_code` |
|--------|-----------|--------------|
| 401 | Missing or invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Role is `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Conversation exists but belongs to another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Conversation ID does not exist in the system | `CONVERSATION_NOT_FOUND` |
| 422 | `conversation_id` is not a valid UUID | Pydantic validation detail |

**Response field notes**:
- `messages`: ordered `sent_at ASC`, tie-broken by `id ASC`. Full, untruncated bodies (SR-05 — truncation is inbox-only).
- `messages[].status`: after this call, every inbound message will be `read` (the call marks them read before returning).
- `client_contact`: `null` when absent — the frontend renders "—".
- `ai_placeholders`: always six entries, all `available: false`. Reserved for future AI specs; structure is forward-compatible (future specs flip `available` and add result fields without a breaking change).

---

## Side-Effect Contract: Mark-as-Read

| Aspect | Behavior |
|--------|----------|
| Trigger | The `GET` detail request itself (no separate endpoint) |
| Scope | `conversation_id` + JWT `tenant_id` + `direction = inbound` + `status = unread` |
| Effect | Matching messages transition `unread → read` |
| Outbound messages | Never modified (AC-08) |
| Idempotency | Second open updates 0 rows; still returns 200 (AC-09) |
| Cross-tenant | A 403 request performs no update (the tenant check precedes the update) |
| Consistency | Update committed in the same transaction; returned thread reflects post-read state |
| Downstream | Inbox `total_unread` (Spec 004) decreases on the next inbox load (AC-10) |

---

## Frontend Routes

| Path | Component | Guard | Note |
|------|-----------|-------|------|
| `/conversations/:id` | `ConversationDetailPage` | `ProtectedRoute` + `RoleGuard(["staff", "manager"])` | **Replaces** the Spec 004 stub component on this same route |

---

## Frontend State → View Mapping

| Hook state | View rendered |
|-----------|---------------|
| `isLoading` | Skeleton loader (header + thread placeholders) |
| `isForbidden` (403) | "You don't have access to this conversation." + link to inbox |
| `isNotFound` (404) | "Conversation not found." + "Back to inbox" button |
| `error` (network/5xx) | Generic error + retry affordance |
| `data` present | `ClientHeader` + `MessageThread` + six `AiPlaceholderPanel`s |

---

## Cross-Cutting Behaviour

| Scenario | HTTP Status | Mark-as-read runs | Audit logged |
|----------|-------------|-------------------|--------------|
| Valid request, messages returned | 200 | Yes | No (read view) |
| Valid request, empty thread | 200 | Yes (0 rows) | No |
| Cross-tenant conversation | 403 | No | Yes — `cross_tenant_forbidden` |
| Platform Admin token | 403 | No | Yes — `insufficient_role` |
| Non-existent conversation | 404 | No | No |
| Missing/expired token | 401 | No | No |
| Malformed UUID | 422 | No | No |

---

## AI Placeholder Contract

The `ai_placeholders` object is the authoritative source for the six future-feature panels. For this feature every entry is `{ "available": false, "label": "<panel title>" }`. The frontend renders one non-interactive "Coming soon" panel per entry. A future AI spec will set `available: true` and extend each placeholder with result fields (e.g. `intent: { available: true, label: "AI Intent", value: "pricing_inquiry", confidence: 0.92 }`) — an additive, non-breaking change.
