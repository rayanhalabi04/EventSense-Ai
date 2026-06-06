# Research: Message Detail Page

**Branch**: `005-message-detail-page` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: 404 vs 403 — Existence Check Strategy

**Decision**: Fetch the conversation by primary key **without** a tenant filter, then branch:
- row is `None` → **404 Not Found**
- row exists but `tenant_id` mismatches the JWT → **403 Forbidden**
- row exists and `tenant_id` matches → **200 OK**

```python
conv = await session.get(Conversation, conversation_id)
if conv is None:
    raise NotFoundError("Conversation not found")
if conv.tenant_id != tenant_id:
    raise ForbiddenError("Conversation belongs to another tenant")
```

**Rationale**: The spec (SR-04) explicitly requires distinguishing "does not exist" (404) from "exists but not yours" (403). A single `WHERE id = :id AND tenant_id = :tid` query collapses both into 404 and cannot satisfy the requirement. The two-step approach is the only way to return 403 for the cross-tenant case.

**Leakage analysis**: Returning 403 for a cross-tenant ID does reveal that *some* conversation with that UUID exists. This is acceptable because conversation IDs are random UUIDs (not enumerable) and no conversation *content* (client name, contact, messages) is ever returned on the 403 path. The 404 branch deliberately does not confirm cross-tenant existence in its message, preventing tenant enumeration via differential responses for IDs the caller cannot see.

**Alternatives considered**:
- Single tenant-scoped query returning 404 for both: simpler but violates SR-04. Rejected.
- Always 404 for security-through-obscurity: rejected because the spec mandates 403 for the wrong-tenant case (and 403 is the established Spec 001 cross-tenant behavior).

---

## Decision 2: Mark-as-Read Trigger and Scope

**Decision**: Mark-as-read runs as a side effect of the `GET` detail request, inside the same DB transaction, **before** the messages are read back — so the returned thread already reflects `read` status. Scope is strictly `direction = inbound AND status = unread` for the target conversation within the authenticated tenant.

```python
UPDATE messages
SET    status = 'read'
WHERE  conversation_id = :id
  AND  tenant_id       = :tenant_id
  AND  direction       = 'inbound'
  AND  status          = 'unread'
```

**Rationale**:
- The spec (US2, FR-008) defines "opening the conversation" as the trigger — no explicit user action. Running it server-side on GET is the simplest reliable implementation.
- Outbound messages (agency-sent) are inherently "seen" and carry no actionable unread state, so they are excluded (FR-008, AC-08).
- The `AND status = 'unread'` predicate makes the update idempotent: a second open updates zero rows and returns 200 (AC-09). No read-modify-write race because the UPDATE is atomic at the row level.
- Running it before the SELECT means the response is internally consistent (no message shows `unread` after the same request marked it read).

**Note on REST semantics**: A `GET` with a write side effect is technically non-idempotent at the data level on the *first* call. This is a pragmatic, well-scoped exception (a common "mark seen on view" pattern). The write is itself idempotent after the first call, and there is no separate body/parameter to make this a PATCH for MVP. A future "explicit mark read" feature can add a dedicated `PATCH` without changing this behavior.

**Alternatives considered**:
- Separate `PATCH /conversations/{id}/read` called by the frontend after render: adds a round-trip and a race between render and patch; deferred to the post-MVP explicit-action feature.
- Mark read per-message as each scrolls into view: out of scope; over-engineered for MVP.

---

## Decision 3: Message Ordering

**Decision**: Messages are returned ordered by `sent_at ASC` (oldest first), matching a natural top-to-bottom chat reading order. Ordering is done in SQL, not in Python.

**Rationale**: Chat threads read oldest→newest top-to-bottom. SQL `ORDER BY sent_at ASC` keeps ordering authoritative server-side and pagination-ready for the future. A B-tree index on `messages(conversation_id, sent_at)` makes this efficient.

**Tie-breaker**: If two messages share an identical `sent_at`, add `id ASC` as a stable secondary sort to guarantee deterministic ordering across requests (important for test stability).

---

## Decision 4: Index for Thread Retrieval

**Decision**: Ensure a composite B-tree index exists on `messages(conversation_id, sent_at)`. If Spec 001/003 already created it, no migration is needed; otherwise add one Alembic migration.

**Rationale**: The detail thread query filters by `conversation_id` and orders by `sent_at`. The composite index serves both the filter and the sort in one structure. The inbox (Spec 004) also benefits from the same index for its latest-message subquery, so it is likely already present — the plan treats the migration as conditional.

**Action**: During implementation, inspect existing migrations / `\d messages`. Add the index migration only if absent.

---

## Decision 5: Response Shape — Full Bodies + AI Placeholders

**Decision**: The detail response returns **full** message bodies (no truncation — truncation is an inbox-only concern, SR-05) plus a static `ai_placeholders` object enumerating the six future panels.

```json
{
  "conversation_id": "uuid",
  "client_name": "Alice Johnson",
  "client_contact": "+44 7700 900123",
  "conversation_status": "open",
  "created_at": "2026-06-03T09:00:00Z",
  "updated_at": "2026-06-03T10:00:00Z",
  "messages": [
    {
      "id": "uuid",
      "body": "full untruncated body…",
      "sent_at": "2026-06-03T09:00:00Z",
      "direction": "inbound",
      "status": "read"
    }
  ],
  "ai_placeholders": {
    "intent": { "available": false, "label": "AI Intent" },
    "risk": { "available": false, "label": "Risk / Sentiment" },
    "rag_sources": { "available": false, "label": "Knowledge Sources" },
    "suggested_reply": { "available": false, "label": "Suggested Reply" },
    "task_creation": { "available": false, "label": "Create Task" },
    "escalation": { "available": false, "label": "Escalate" }
  }
}
```

**Rationale**:
- Full bodies are required to read the thread (the whole point of the page); truncation only ever applied to the inbox preview to bound that payload (SR-05).
- A static `ai_placeholders` block lets the frontend render the six panels from data, and lets a future AI spec flip `available: true` and add result fields (e.g. `intent.value`) **without a breaking contract change** — the AI Behavior section of the spec mandates this extensibility.

**Alternatives considered**:
- Hardcode the six panels purely in the frontend with no backend block: simpler now, but a future AI spec would have to add the block and re-wire the frontend. Including it now is cheap and forward-compatible.

---

## Decision 6: Frontend State Machine (loading / error / forbidden / not-found / data)

**Decision**: `useConversationDetail` exposes discrete boolean flags (`isLoading`, `isForbidden`, `isNotFound`, `error`) plus `data`. `ConversationDetailPage` renders exactly one view based on these, in priority order: loading → forbidden → notFound → error → data.

**Rationale**: The spec defines four distinct non-success states (loading, error, forbidden, not-found) each with different copy and affordances (403 = "you don't have access"; 404 = "conversation not found" + back-to-inbox link). Discrete flags keep the page's branching explicit and testable, rather than overloading a single `error` string.

---

## Decision 7: Route Replacement (Spec 004 stub → real page)

**Decision**: Spec 004 registered `/conversations/:id` as a placeholder ("Conversation detail coming soon"). This feature **replaces** that route's component with `ConversationDetailPage`. No new route is added — the existing route target changes in `App.tsx`.

**Rationale**: Avoids a duplicate/competing route. The inbox row click (Spec 004) already navigates to `/conversations/{id}`; pointing that route at the real page completes the inbox→detail workflow with no inbox changes.

---

## Decision 8: No AI / Workflow Logic

**Decision**: This feature implements **zero** AI or workflow logic. Intent, risk, RAG, suggested replies, task creation, and escalation are presented only as non-functional placeholder panels. No model calls, no scoring, no retrieval, no mutations.

**Rationale**: Explicit scope boundary from the feature request. Placeholders communicate the roadmap and reserve layout space; the actual capabilities arrive in dedicated future specs.

---

## Decision 9: Deferred Items

| Item | Reason deferred |
|------|----------------|
| AI intent / risk / RAG / suggested reply | Dedicated future AI specs; placeholders only |
| Task creation / escalation workflow | Dedicated future specs; placeholders only |
| Reply / compose | Requires a write/compose feature; post-MVP |
| Explicit mark read/unread (PATCH) | Post-MVP; current mark-read is automatic on open |
| Status mutation from detail page | Status is read-only here; post-MVP |
| Thread pagination | Full thread loaded for MVP scale |
| Real-time updates (WebSocket) | Post-MVP |
| Real WhatsApp API | Out of scope entirely |
