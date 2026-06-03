# API Contracts: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Phase**: 1 — Design

All endpoints are prefixed with `/api/v1`. All protected endpoints require a valid JWT Bearer token. `tenant_id` is **never** accepted from the client — it is always extracted from the JWT.

---

## Authentication Assumptions

- Auth endpoints (`POST /auth/token`, `POST /auth/refresh`) are out of scope for this feature. They are assumed to exist and to return a JWT containing `{ sub: user_id, tenant_id: uuid, role: string, exp: int }`.
- The `get_current_tenant_context` FastAPI dependency validates the token and returns a `TenantContext(tenant_id, user_id, role)` dataclass.
- Routes annotated with `[admin_required]` reject requests where `role != tenant_admin`.
- Routes annotated with `[super_admin_required]` reject requests where `role != super_admin`.

---

## Tenant Context

### `GET /api/v1/tenants/me`

Returns the current user's tenant metadata.

**Auth**: Any authenticated user.

**Response 200**:
```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "name": "Elegant Weddings",
  "slug": "elegant-weddings",
  "is_active": true
}
```

**Response 401**: Missing or invalid token.

---

## Tenant Provisioning (Super Admin)

### `POST /api/v1/admin/tenants` `[super_admin_required]`

Provisions a new tenant and its initial Tenant Admin user.

**Request body**:
```json
{
  "name": "Sunset Events",
  "slug": "sunset-events",
  "admin_email": "admin@sunset-events.com",
  "admin_full_name": "Jane Smith",
  "admin_password": "••••••••"
}
```

**Response 201**:
```json
{
  "tenant_id": "uuid",
  "admin_user_id": "uuid"
}
```

**Response 409**: Slug or email already exists.
**Response 422**: Validation error.

---

### `GET /api/v1/admin/tenants` `[super_admin_required]`

Lists all tenants (metadata only — no content data).

**Response 200**:
```json
{
  "items": [
    { "id": "uuid", "name": "Elegant Weddings", "slug": "elegant-weddings", "is_active": true, "created_at": "..." }
  ],
  "total": 2
}
```

---

## Conversations

### `GET /api/v1/conversations`

Lists conversations for the authenticated tenant.

**Auth**: Any tenant user.
**Query params**: `status` (open/closed/escalated), `page`, `page_size` (default 20).

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "client_name": "Alice Johnson",
      "client_contact": "alice@example.com",
      "status": "open",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

---

### `POST /api/v1/conversations`

Creates a new conversation.

**Auth**: Any tenant user.

**Request body**:
```json
{
  "client_name": "Alice Johnson",
  "client_contact": "alice@example.com"
}
```

**Response 201**:
```json
{ "id": "uuid", "status": "open", "created_at": "..." }
```

---

### `GET /api/v1/conversations/{conversation_id}`

Returns a single conversation with its messages.

**Auth**: Any tenant user.

**Response 200**: Conversation + paginated messages.
**Response 403**: `conversation.tenant_id != ctx.tenant_id` → blocked and audit-logged.
**Response 404**: Conversation does not exist.

**Security note**: 403 is returned for cross-tenant IDs (not 404) to prevent timing-based enumeration. The response body is `{ "detail": "forbidden" }` with no additional context.

---

## Messages

### `POST /api/v1/conversations/{conversation_id}/messages`

Posts a new outbound message from an agent.

**Auth**: Any tenant user.

**Request body**:
```json
{ "body": "Thank you for reaching out! ..." }
```

**Response 201**: `{ "id": "uuid", "direction": "outbound", "sent_at": "..." }`
**Response 403**: Cross-tenant conversation.

---

## Documents

### `GET /api/v1/documents`

Lists documents for the authenticated tenant.

**Query params**: `status`, `page`, `page_size`.
**Response 200**: Paginated document list (no `storage_path` in response).

---

### `POST /api/v1/documents`

Initiates a document upload.

**Auth**: Any tenant user.
**Content-Type**: `multipart/form-data`
**Form fields**: `file` (binary), `filename` (string).

**Response 202**:
```json
{ "document_id": "uuid", "status": "pending" }
```

**Notes**: The endpoint creates the `documents` record immediately (status=`pending`) and enqueues the chunking job. The response is 202 Accepted because processing is asynchronous. `tenant_id` is set from the JWT — never from the form body.

---

### `GET /api/v1/documents/{document_id}`

Returns document metadata and processing status.

**Response 200**: Document record (excluding `storage_path`).
**Response 403**: Cross-tenant document.

---

## Suggested Replies

### `GET /api/v1/conversations/{conversation_id}/suggested-replies`

Lists AI-generated reply drafts for a conversation.

**Response 200**: List of suggested reply objects.
**Response 403**: Cross-tenant conversation.

---

### `PATCH /api/v1/suggested-replies/{reply_id}`

Accepts or rejects a suggested reply.

**Request body**: `{ "status": "accepted" | "rejected" }`
**Response 200**: Updated reply object.
**Response 403**: Cross-tenant reply.

---

## Tasks

### `GET /api/v1/tasks`

Lists follow-up tasks for the authenticated tenant.

**Query params**: `status`, `assigned_to_user_id`, `conversation_id`, `page`, `page_size`.
**Response 200**: Paginated task list.

---

### `POST /api/v1/tasks`

Creates a new follow-up task.

**Request body**:
```json
{
  "title": "Send venue brochure",
  "description": "...",
  "conversation_id": "uuid",
  "assigned_to_user_id": "uuid",
  "due_at": "2026-06-15T10:00:00Z"
}
```

**Response 201**: Created task.

---

### `PATCH /api/v1/tasks/{task_id}`

Updates task status or assignment.

**Response 200**: Updated task.
**Response 403**: Cross-tenant task.

---

## Escalations

### `POST /api/v1/conversations/{conversation_id}/escalate`

Escalates a conversation for human review.

**Request body**: `{ "reason": "Client is unhappy with venue options." }`
**Response 201**: Escalation record.
**Response 403**: Cross-tenant conversation.

---

## Audit Logs

### `GET /api/v1/audit-logs` `[admin_required]`

Returns audit log entries for the authenticated tenant. Tenant Admins see only their own tenant's logs.

**Query params**: `action`, `outcome`, `actor_user_id`, `from`, `to`, `page`, `page_size`.

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "actor_user_id": "uuid",
      "action": "cross_tenant_access_attempt",
      "resource_type": "conversation",
      "resource_id": "uuid",
      "outcome": "blocked",
      "ip_address": "203.0.113.42",
      "created_at": "..."
    }
  ],
  "total": 12
}
```

**Super Admin variant**: `GET /api/v1/admin/audit-logs?tenant_id=uuid` — can query any tenant's logs. Requires `super_admin` role.

---

## Cross-Cutting Security Behaviour

| Scenario | HTTP Status | Audit Log Entry |
|----------|-------------|-----------------|
| Valid request, resource matches JWT tenant | 200/201/202 | Written for sensitive actions (uploads, AI calls) |
| JWT missing or expired | 401 | Not written |
| JWT valid, role insufficient for endpoint | 403 | Written with `outcome=blocked`, `action=insufficient_role` |
| JWT valid, resource belongs to different tenant | 403 | Written with `outcome=blocked`, `action=cross_tenant_access_attempt` |
| `tenant_id` supplied in request body | Body field silently ignored; session value used | Written with `action=tenant_id_override_attempt` if mismatch detected |

---

## Error Response Shape

All error responses follow a consistent shape:

```json
{
  "detail": "forbidden",
  "error_code": "CROSS_TENANT_ACCESS"
}
```

Error codes relevant to this feature:

| Code | Meaning |
|------|---------|
| `CROSS_TENANT_ACCESS` | Resource belongs to a different tenant |
| `INSUFFICIENT_ROLE` | User role does not permit this action |
| `TENANT_ID_OVERRIDE` | Client attempted to supply a different `tenant_id` |
| `RECORD_MISSING_TENANT` | Write rejected due to null `tenant_id` (integrity error) |
