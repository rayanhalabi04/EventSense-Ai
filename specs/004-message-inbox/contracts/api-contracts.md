# API Contracts: Message Inbox

**Branch**: `004-message-inbox` | **Phase**: 1 — Design

---

## GET /api/v1/inbox

Returns a paginated, filtered, and optionally searched list of tenant conversations for the authenticated user's inbox.

**Auth**: Bearer token; requires `staff` or `manager` role.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `unread_only` | boolean | `false` | When `true`, returns only conversations with at least one unread message |
| `status` | string | `null` | Filter by conversation status: `open`, `closed`, or `escalated`. Omit for all. |
| `search` | string | `null` | Search term. Blank/omitted means no search. Frontend ignores 0-1 character terms; backend normalizes blank to no search. |
| `page` | integer | `1` | Page number (1-indexed). |
| `page_size` | integer | `20` | Items per page. Fixed at 20 for MVP; max 100. |

**Response 200**:
```json
{
  "items": [
    {
      "conversation_id":          "a0b1c2d3-0000-0000-0000-000000000011",
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
  ],
  "total":        25,
  "total_unread": 8,
  "page":         1,
  "page_size":    20,
  "total_pages":  2
}
```

**Empty inbox** (no conversations in tenant, no filters applied):
```json
{
  "items":        [],
  "total":        0,
  "total_unread": 0,
  "page":         1,
  "page_size":    20,
  "total_pages":  0
}
```

**Filtered/searched with no matches**:
```json
{
  "items":        [],
  "total":        0,
  "total_unread": 3,
  "page":         1,
  "page_size":    20,
  "total_pages":  0
}
```
Note: `total_unread` is always the tenant-wide unread count — it does not reflect the current filter state.

**Failure responses**:

| Status | Condition | `error_code` |
|--------|-----------|--------------|
| 401 | Missing or invalid token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Role is `platform_admin` | `INSUFFICIENT_ROLE` |
| 422 | `status` value is not a valid enum member | Pydantic validation detail |
| 422 | `page` < 1 | Pydantic validation detail |

**Response field notes**:
- `latest_message_preview`: body of the most recent message, truncated to 100 characters server-side. `null` if the conversation has no messages; the UI displays "No messages yet."
- `latest_message_at`: `sent_at` of the most recent message. `null` if no messages.
- `latest_message_direction`: `"inbound"` or `"outbound"`. `null` if no messages.
- `total`: count of conversations matching the active filters (used for pagination math).
- `total_unread`: **always** the tenant-wide count of conversations with ≥1 unread message, regardless of filters. Used to drive the nav badge.

---

## Frontend Route

| Path | Component | Guard |
|------|-----------|-------|
| `/inbox` | `InboxPage` | `ProtectedRoute` + `RoleGuard(["staff", "manager"])` |
| `/conversations/:id` | `ConversationDetailPage` (stub/placeholder) | `ProtectedRoute` (navigation target only; detail is Spec 005) |

---

## GET /api/v1/inbox/summary

Returns lightweight tenant-scoped counts for the navbar/sidebar badge without loading the full inbox page.

**Auth**: Bearer token; requires `staff` or `manager` role.

**Response 200**:

```json
{
  "total_open": 12,
  "unread_or_new": 3,
  "high_risk_placeholder": 0
}
```

**Notes**:
- `unread_or_new` is the number of conversations with at least one unread message.
- `high_risk_placeholder` remains `0` until the later risk-detection feature exists.
- All counts are tenant-scoped using the authenticated user's `tenant_id`.

---

## Cross-Cutting Behaviour

| Scenario | HTTP Status | Audit logged |
|----------|-------------|--------------|
| Valid request, items returned | 200 | No (read operations are not audit-logged) |
| Valid request, empty results | 200 (empty items array) | No |
| Platform Admin token | 403 | Yes — `insufficient_role` |
| Missing or expired token | 401 | No |
| Blank/omitted search | 200 | No; treated as no search |
| 0-1 character frontend search | No request | Frontend keeps current list or clears search param |
| Invalid status enum | 422 | No |

---

## Filter Interaction Rules

| Filter combination | Behaviour |
|-------------------|-----------|
| `unread_only=true` | Only conversations where `unread_count > 0` |
| `status=open` | Only conversations with `status=open` |
| `unread_only=true` + `status=open` | Conversations that are BOTH unread AND open |
| `search=alice` | Conversations where `client_name`, `client_contact`, or any `messages.body` ILIKE `%alice%` |
| `search=alice` + `status=closed` | Conversations matching "alice" that are also `closed` |
| All three combined | All three criteria must be satisfied (AND logic) |

---

## Unread Badge Integration

`GET /api/v1/inbox/summary` is the preferred source for the nav badge before the inbox page loads. The `total_unread` field in `GET /api/v1/inbox` remains useful after the inbox page has loaded and should match `summary.unread_or_new`.
