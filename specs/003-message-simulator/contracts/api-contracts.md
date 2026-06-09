# API Contracts: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator` | **Phase**: 1 — Design

All endpoints are prefixed `/api/v1/simulator`. All require a valid JWT with `staff` or `manager` role. `tenant_id` is derived from the JWT — never from the request body.

---

## POST /api/v1/simulator/messages

Injects a simulated inbound client message into the authenticated tenant's workspace.

**Auth**: Bearer token, requires `staff` or `manager` role.

**Request body** (`application/json`):
```json
{
  "client_name":    "Alice Johnson",
  "client_contact": "+44 7700 900123",
  "body":           "Can you send me your wedding package prices?",
  "conversation_id": null
}
```

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `client_name` | string | Required only when `conversation_id` is omitted | Non-empty after strip when provided |
| `client_contact` | string | No | Phone or email; `null` if omitted |
| `body` | string | Yes | Non-empty after strip; ≤ 4,000 characters |
| `conversation_id` | UUID | No | If supplied, must belong to authenticated tenant |

**Success — Response 201**:
```json
{
  "message_id":          "uuid",
  "conversation_id":     "uuid",
  "is_new_conversation": true,
  "conversation_status": "open",
  "tenant_id":           "uuid"
}
```

**Failure responses**:

| Status | Condition | `error_code` |
|--------|-----------|--------------|
| 401 | Missing or invalid token | `MISSING_TOKEN` / `INVALID_TOKEN` |
| 403 | Role is `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | `conversation_id` belongs to a different tenant | `CROSS_TENANT_ACCESS` |
| 422 | `body` is empty or whitespace-only | Pydantic validation detail |
| 422 | `body` exceeds 4,000 characters | Pydantic validation detail |
| 422 | neither `conversation_id` nor non-empty `client_name` is supplied | Pydantic validation detail |

**Audit event**: On success, record/emit one `simulator_message_created` event if audit infrastructure exists, including `actor_user_id`, `resource_type=message`, `resource_id=message_id`, `detail.conversation_id`, `detail.client_name` when available, `detail.is_new_conversation`, and `detail.reopened`.

**Notes**:
- `tenant_id` in the response reflects the JWT-derived value — never the client's input.
- The request must provide either `conversation_id` or `client_name`. If `conversation_id` is provided, `client_name` is optional because the conversation already identifies the client.
- If `conversation_id` is supplied and the conversation is `closed`, the endpoint re-opens it before appending the message.
- If no `conversation_id` is supplied, the backend resolves (or creates) a conversation by matching `(LOWER(client_name), client_contact)` within the tenant.

---

## GET /api/v1/simulator/conversations

Returns the list of existing conversations for the authenticated tenant — used to populate the conversation selector dropdown in the simulator UI.

**Auth**: Bearer token, requires `staff` or `manager` role.

**Query params**: None for MVP. Future: `?status=open|closed|all`.

**Response 200**:
```json
{
  "items": [
    {
      "id":             "uuid",
      "client_name":    "Alice Johnson",
      "client_contact": "+44 7700 900123",
      "status":         "open",
      "message_count":  3,
      "updated_at":     "2026-06-03T10:00:00Z"
    }
  ],
  "total": 1
}
```

**Notes**:
- Returns only the authenticated tenant's conversations (tenant filter always applied).
- Ordered by `updated_at DESC` — most recently active first.
- Does not include message content — only metadata needed for the dropdown.

---

## Cross-Cutting Behaviour

| Scenario | HTTP Status | `error_code` | Audit logged |
|----------|-------------|--------------|--------------|
| Valid submission, new conversation | 201 | — | Yes — `simulator_message_created` |
| Valid submission, existing conversation | 201 | — | Yes — `simulator_message_created` |
| Valid submission, closed conversation re-opened | 201 | — | Yes, one event — includes `detail.reopened=true` |
| Empty `body` | 422 | Pydantic detail | No |
| Body > 4,000 chars | 422 | Pydantic detail | No |
| Missing both `conversation_id` and `client_name` | 422 | Pydantic detail | No |
| `conversation_id` from other tenant | 403 | `CROSS_TENANT_ACCESS` | Yes |
| `platform_admin` role | 403 | `INSUFFICIENT_ROLE` | Yes |
| Missing token | 401 | `MISSING_TOKEN` | No |

---

## Frontend Route

| Path | Component | Guard |
|------|-----------|-------|
| `/simulator` | `SimulatorPage` | `ProtectedRoute` + `RoleGuard(["staff", "manager"])` |
