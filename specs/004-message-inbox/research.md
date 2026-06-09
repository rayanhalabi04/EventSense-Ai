# Research: Message Inbox

**Branch**: `004-message-inbox` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: SQL Query Strategy — Latest Message Per Conversation

**Decision**: Use a correlated subquery to fetch the latest message for each conversation in a single SQL round-trip. The subquery selects the most-recent message `id` per conversation ordered by `sent_at DESC LIMIT 1`.

```sql
SELECT
    c.id,
    c.client_name,
    c.client_contact,
    c.status,
    c.updated_at,
    m.body           AS latest_body,
    m.sent_at        AS latest_sent_at,
    m.direction      AS latest_direction,
    (
        SELECT COUNT(*)
        FROM   messages m2
        WHERE  m2.conversation_id = c.id
        AND    m2.tenant_id       = c.tenant_id
        AND    m2.status          = 'unread'
    ) AS unread_count
FROM  conversations c
LEFT JOIN messages m ON m.id = (
    SELECT id
    FROM   messages
    WHERE  conversation_id = c.id
    ORDER  BY sent_at DESC
    LIMIT  1
)
WHERE c.tenant_id = :tenant_id
  [AND c.status = :status]           -- optional status filter
  [AND unread_count > 0]             -- unread_only filter (applied via HAVING or subquery)
  [AND (
       c.client_name    ILIKE :search_pattern
    OR c.client_contact ILIKE :search_pattern
    OR EXISTS (
         SELECT 1 FROM messages ms
         WHERE  ms.conversation_id = c.id
         AND    ms.body ILIKE :search_pattern
         AND    ms.tenant_id = :tenant_id
       )
  )]
ORDER BY c.updated_at DESC
LIMIT  :page_size
OFFSET :offset
```

**Rationale**:
- A correlated subquery on `messages` is clean and readable in SQLAlchemy. For MVP scale (hundreds of conversations per tenant), it's fast enough with the existing B-tree indexes on `(conversation_id, sent_at)`.
- A window function (`ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY sent_at DESC)`) would be more performant at high scale but is harder to express cleanly in SQLAlchemy ORM. Deferred to post-MVP.
- The `unread_count` correlated subquery reuses the `tenant_id` filter, so no cross-tenant data leaks even in an aggregate.

**Alternatives considered**:
- Window function approach: better at scale; deferred.
- Separate N+1 queries (one per conversation): too slow. Rejected.
- Denormalized `latest_message_id` FK on `conversations`: good performance, but requires maintaining the denormalisation on every message write. Deferred.

---

## Decision 2: Unread Filter Implementation

**Decision**: The `unread_only` filter is implemented by wrapping the main query in a subquery and filtering on `unread_count > 0`. In SQLAlchemy this is achieved by selecting from the subquery with a `HAVING` or by using a CTE.

Pragmatic SQLAlchemy approach:
```python
# Build the base query as a subquery, then filter on unread_count
stmt = (
    select(Conversation, ...)
    .where(Conversation.tenant_id == tenant_id)
    ...
)
if unread_only:
    stmt = stmt.having(unread_count_col > 0)  # or add to WHERE via subquery
```

**Rationale**: Applying the unread filter at the SQL level (not Python post-filtering) keeps pagination counts accurate. If we fetched all conversations and filtered in Python, page 1 might have fewer than 20 items even when 50 unread conversations exist.

---

## Decision 3: Search Strategy

**Decision**: Full-text search via `ILIKE` pattern matching. The search term is prefixed and suffixed with `%` (`%:term%`). It checks:
1. `conversations.client_name ILIKE :pattern`
2. `conversations.client_contact ILIKE :pattern`
3. `EXISTS (SELECT 1 FROM messages WHERE conversation_id = c.id AND body ILIKE :pattern AND tenant_id = :tid)`

These three conditions are combined with `OR`. Search minimum: 2 characters (enforced by Pydantic validator — terms shorter than 2 chars are rejected with 422).

**Rationale**:
- `ILIKE` is built into PostgreSQL and requires no additional extension for MVP scale.
- The `EXISTS` subquery on messages is efficient when `(conversation_id, tenant_id)` is indexed (both indexes exist from Spec 001).
- PostgreSQL full-text search (`tsvector`/`tsquery`) would be better at scale but requires additional index setup. Deferred.

**Alternatives considered**:
- PostgreSQL full-text search: better for large corpora; deferred.
- Client-side filtering: breaks pagination accuracy. Rejected.

---

## Decision 4: Response Shape and Preview Truncation

**Decision**: Preview truncation to 100 characters is applied in Python after the query returns the raw body. The `latest_message_preview` field in the response is always ≤ 100 characters with a trailing `…` if truncated.

```python
def truncate_preview(body: str | None, max_len: int = 100) -> str | None:
    if body is None:
        return None
    return body[:max_len] + ("…" if len(body) > max_len else "")
```

The full `InboxItemResponse` shape:
```json
{
  "conversation_id":          "uuid",
  "client_name":              "Alice Johnson",
  "client_contact":           "+44 7700 900123",
  "latest_message_preview":   "Can you send me your wedding package prices?",
  "latest_message_at":        "2026-06-03T10:00:00Z",
  "latest_message_direction": "inbound",
  "unread_count":             2,
  "has_unread":               true,
  "conversation_status":      "open",
  "updated_at":               "2026-06-03T10:00:00Z"
}
```

The top-level response includes:
```json
{
  "items":        [...],
  "total":        25,
  "total_unread": 8,
  "page":         1,
  "page_size":    20,
  "total_pages":  2
}
```

`total_unread` is a separate `COUNT(DISTINCT conversation_id)` query that counts all conversations in the tenant with at least one unread message — it ignores any active filters so the nav badge always reflects the true tenant-wide unread state.

---

## Decision 5: URL-Preserved Filter State

**Decision**: All filter and search state is encoded in URL query parameters. The frontend `useInbox` hook reads from `URLSearchParams` on mount and writes back on every filter/search change using `react-router`'s `useSearchParams`.

```
/inbox?status=open&unread_only=true&search=alice&page=2
```

**Rationale**: Browser back/forward and page refresh restore the exact same filtered view — required by AC-14's "state is preserved" scenario and a standard SPA pattern.

---

## Decision 6: No New Schema Changes

**Decision**: This feature introduces **zero schema changes**. It reads from the existing `conversations` and `messages` tables using the `status` column added in Spec 003. No migrations are needed.

**Rationale**: The inbox is a pure read feature. All required data is already in the database.

---

## Decision 7: Inbox Summary Fetch Strategy

**Decision**: The full inbox response still includes `total_unread`, but the navbar/sidebar badge uses `GET /api/v1/inbox/summary` so counts are available before the inbox page itself loads.

```sql
SELECT COUNT(DISTINCT conversation_id)
FROM   messages
WHERE  tenant_id = :tenant_id
AND    status    = 'unread'
```

The summary endpoint also returns `total_open` and `high_risk_placeholder=0` for later risk-detection compatibility.

**Rationale**: The badge should work before a user opens the inbox. A lightweight summary endpoint is simple, tenant-scoped, and avoids loading paginated list data just to draw navigation.

**Alternatives considered**:
- Rely only on `total_unread` from the full inbox response: simpler but badge is stale/missing until the inbox is loaded. Rejected.
- Real-time push via WebSocket: excellent UX but overkill for MVP. Deferred.

---

## Decision 8: Frontend Component Architecture

**Decision**: 5 components + 1 hook + 1 API module:

```
InboxPage.tsx          → /inbox route; orchestrates all sub-components
  InboxFilters.tsx     → read-status toggle + conversation-status select
  InboxSearch.tsx      → debounced (300ms) text input; ignores 0-1 char terms
  InboxList.tsx        → renders list or empty state
    InboxItem.tsx      → single conversation row/card
    InboxEmptyState.tsx→ global empty vs filtered empty variant
  InboxPagination.tsx  → previous/next + page indicator

useInbox.ts            → reads/writes URLSearchParams; fetches from API; manages loading/error
api/inbox.ts           → getInbox(params), getInboxSummary() Axios calls
```

`useInbox` calls `getInbox` on mount and on every filter/search/page change. It exposes `{ items, total, totalUnread, isLoading, error, filters, setFilter, setSearch, setPage }`.

---

## Decision 9: Deferred Items

| Item | Reason deferred |
|------|----------------|
| Mark as read / mark as unread | Separate feature; requires a PATCH /messages/{id}/read endpoint |
| Real-time inbox updates (WebSocket) | Post-MVP; would require a publish/subscribe layer |
| Message detail page | Separate feature (Spec 005); this feature only adds the navigation link |
| PostgreSQL full-text search with tsvector | Post-MVP scalability enhancement |
| Denormalised latest_message_id on conversations | Post-MVP performance optimisation |
| Sort options beyond updated_at DESC | Out of scope per spec |
| Bulk actions | Out of scope per spec |
