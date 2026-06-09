# API Contracts: Audit Logs

**Branch**: `013-audit-logs` | **Phase**: 1 — Design

**Auth (all read endpoints)**: Bearer JWT. **Tenant-wide read** (`GET /api/audit-logs`, `GET /api/audit-logs/{id}`, `GET /api/escalations/{id}/audit-logs`) requires `manager`. **Message-scoped read** (`GET /api/messages/{id}/audit-logs`) allows `manager`, and `staff` only when `AUDIT_STAFF_MESSAGE_VIEW_ENABLED` (security-severity entries excluded for staff). Platform Admin → 403. `tenant_id` and `actor_user_id` are always derived from the JWT; any client-supplied tenant is ignored. Every read resolves the entry/message/entity tenant first (404 if it does not exist; 403 if it exists in another tenant — consistent with Specs 005–012). **Audit entries are append-only**: there is no create/update/delete endpoint for tenant users; the only write path is the internal `AuditService.log_event(...)` function (and the optional service-authenticated internal endpoint below). **Writing an entry is best-effort and never surfaces an error to the primary workflow.**

---

## 1. GET /api/audit-logs

Tenant-wide audit log list (dashboard). **`manager` only.** Newest-first, filtered, paginated.

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `event_type` | string (AuditEventType) | — | Filter by event type |
| `actor_type` | string (AuditActorType) | — | `user` / `system` / `ai_service` |
| `actor_user_id` | UUID | — | Filter by human actor |
| `severity` | string (AuditSeverity) | — | `info` / `warning` / `error` / `security` |
| `entity_type` | string (AuditEntityType) | — | Filter by related entity type |
| `entity_id` | UUID | — | Filter by related entity id |
| `message_id` | UUID | — | Filter by related message |
| `created_from` | ISO datetime | — | Start of date range (inclusive) |
| `created_to` | ISO datetime | — | End of date range (inclusive) |
| `limit` | int | 50 | Page size (bounded by `AUDIT_LIST_MAX_LIMIT`, e.g. 200) |
| `offset` | int | 0 | Page offset |

**Response 200**:
```json
{
  "items": [
    {
      "id": "f7000000-0000-0000-0000-000000000001",
      "created_at": "2026-06-08T10:00:05Z",
      "event_type": "intent_classified",
      "actor_type": "ai_service",
      "actor_user_id": null,
      "severity": "info",
      "entity_type": "classification_result",
      "entity_id": "c6000000-0000-0000-0000-000000000010",
      "message_id": "b1000000-0000-0000-0000-000000000020",
      "redacted_summary": "Classified message as pricing_request (confidence 0.91)."
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```
Note: list items are a metadata summary; fetch a single entry for full `metadata` + `conversation_id` + `request_id`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Caller is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 422 | Invalid filter / enum / date / pagination | validation detail |

---

## 2. GET /api/audit-logs/{audit_log_id}

Fetch a single audit entry with full (redacted) metadata + references. **`manager` only.**

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `audit_log_id` | UUID | The entry to fetch. |

**Response 200**:
```json
{
  "id": "f7000000-0000-0000-0000-000000000001",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "actor_user_id": null,
  "actor_type": "ai_service",
  "event_type": "intent_classified",
  "severity": "info",
  "entity_type": "classification_result",
  "entity_id": "c6000000-0000-0000-0000-000000000010",
  "message_id": "b1000000-0000-0000-0000-000000000020",
  "conversation_id": "a0000000-0000-0000-0000-000000000007",
  "metadata": {
    "classification_id": "c6000000-0000-0000-0000-000000000010",
    "predicted_label": "pricing_request",
    "confidence": 0.91
  },
  "redacted_summary": "Classified message as pricing_request (confidence 0.91).",
  "request_id": "req_8f2a...",
  "created_at": "2026-06-08T10:00:05Z"
}
```
The `metadata` never contains prompts, model internals, secrets, JWTs, API keys, full message text, or any other tenant's data.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Caller is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Entry in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Entry does not exist | `AUDIT_LOG_NOT_FOUND` |
| 422 | `audit_log_id` not a UUID | validation detail |

---

## 3. GET /api/messages/{message_id}/audit-logs

List the audit entries for a specific message, tenant-scoped. **`manager`**, and **`staff`** when `AUDIT_STAFF_MESSAGE_VIEW_ENABLED` (staff view excludes `security`-severity entries).

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The source message. |

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000020",
  "items": [
    {
      "id": "f7000000-0000-0000-0000-000000000001",
      "created_at": "2026-06-08T10:00:05Z",
      "event_type": "intent_classified",
      "actor_type": "ai_service",
      "actor_user_id": null,
      "severity": "info",
      "entity_type": "classification_result",
      "entity_id": "c6000000-0000-0000-0000-000000000010",
      "message_id": "b1000000-0000-0000-0000-000000000020",
      "redacted_summary": "Classified message as pricing_request (confidence 0.91)."
    }
  ],
  "total": 1
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Staff and `AUDIT_STAFF_MESSAGE_VIEW_ENABLED` is false | `STAFF_AUDIT_DISABLED` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 422 | `message_id` not a UUID | validation detail |

---

## 4. GET /api/escalations/{escalation_id}/audit-logs

List the audit entries for a specific escalation (entity-scoped), tenant-scoped. **`manager` only.**

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `escalation_id` | UUID | The escalation. |

**Response 200**:
```json
{
  "escalation_id": "e5000000-0000-0000-0000-000000000001",
  "items": [
    {
      "id": "f7000000-0000-0000-0000-000000000044",
      "created_at": "2026-06-08T11:02:00Z",
      "event_type": "escalation_resolved",
      "actor_type": "user",
      "actor_user_id": "c2000000-0000-0000-0000-000000000099",
      "severity": "info",
      "entity_type": "escalation",
      "entity_id": "e5000000-0000-0000-0000-000000000001",
      "message_id": "b1000000-0000-0000-0000-000000000020",
      "redacted_summary": "Escalation resolved by manager."
    }
  ],
  "total": 1
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Caller is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Escalation in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Escalation does not exist | `ESCALATION_NOT_FOUND` |
| 422 | `escalation_id` not a UUID | validation detail |

---

## 5. POST /api/internal/audit-logs *(optional — internal/system writer)*

Append an audit entry from an **out-of-process** system/AI writer. **Service-authenticated only** (a service credential/shared secret, **not** a tenant JWT). Subject to the same redaction/validation as `AuditService.log_event`. The **primary** write mechanism is the in-process `log_event` function; this endpoint exists only if a writer cannot call it directly.

**Auth**: `X-Internal-Service-Token` header (or mTLS), validated against a configured service secret. Tenant users can never call this endpoint.

**Request body**:
```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "actor_type": "ai_service",
  "actor_user_id": null,
  "event_type": "rag_no_source_found",
  "severity": "warning",
  "entity_type": "rag_retrieval",
  "entity_id": null,
  "message_id": "b1000000-0000-0000-0000-000000000020",
  "conversation_id": "a0000000-0000-0000-0000-000000000007",
  "metadata": { "message_id": "b1000000-0000-0000-0000-000000000020" },
  "redacted_summary": "RAG found no grounded source for the query.",
  "request_id": "req_8f2a..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | UUID | yes | The owning tenant (validated against the service context) |
| `actor_type` | string (AuditActorType) | yes | `user` / `system` / `ai_service` |
| `actor_user_id` | UUID | conditional | Required iff `actor_type=user`; null otherwise |
| `event_type` | string (AuditEventType) | yes | A valid event type |
| `severity` | string (AuditSeverity) | no | Defaults `info` |
| `entity_type` | string (AuditEntityType) | no | Related entity type |
| `entity_id` | UUID | no | Related entity id |
| `message_id` | UUID | no | Related message |
| `conversation_id` | UUID | no | Related conversation |
| `metadata` | object | no | Ids + minimal facts (redacted + size-bounded server-side) |
| `redacted_summary` | string | no | Short sanitized sentence (≤ 500) |
| `request_id` | string | no | Correlation id (≤ 64) |

**Validation rules**:
- Valid service token → else 401/403 (`INVALID_SERVICE_TOKEN`).
- `event_type`/`actor_type`/`severity`/`entity_type` ∈ their enums → 422.
- `actor_user_id` present iff `actor_type=user` → 422.
- `metadata` is redacted (forbidden keys stripped) + size-capped (truncated + `metadata_truncated=true`) — never rejected for size.
- `redacted_summary`/`metadata` must not carry secrets/prompts/JWTs/keys/cross-tenant data (redaction backstop).

**Response 202** (accepted; best-effort semantics):
```json
{ "status": "accepted" }
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401/403 | Missing/invalid service token | `INVALID_SERVICE_TOKEN` |
| 403 | Called with a tenant JWT (not a service) | `INSUFFICIENT_ROLE` |
| 422 | Invalid enum / actor rule / payload | validation detail |

> Even here, a downstream storage failure is best-effort: the endpoint returns `202` and the failure is recorded to app logs/metrics rather than propagated as a 5xx that could destabilize the caller. (Validation errors, by contrast, are returned so misconfiguration is visible.)

---

## No Write/Mutate Endpoints for Tenant Users

There is **no** `POST` (tenant), `PATCH`, `PUT`, or `DELETE` for `/api/audit-logs`. Audit entries are append-only and immutable in the MVP.

| Attempted method | Result |
|------------------|--------|
| `PATCH /api/audit-logs/{id}` | 405 `METHOD_NOT_ALLOWED` (no route) |
| `DELETE /api/audit-logs/{id}` | 405 `METHOD_NOT_ALLOWED` (no route) |
| `POST /api/audit-logs` (tenant user) | 405 `METHOD_NOT_ALLOWED` (no route) |

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Manager lists/get tenant logs | 200 | none (tenant-scoped, paginated) |
| Manager filters (event/actor/date/entity/severity) | 200 | none |
| Staff lists tenant-wide logs | 403 | none |
| Staff lists message-scoped logs (enabled) | 200 | security entries excluded |
| Staff lists message-scoped logs (disabled) | 403 | none |
| Any read, cross-tenant entry/message/entity | 404/403 | none |
| Any read, Platform Admin | 403 | none |
| Update/delete an entry | 405 | none (append-only) |
| Internal write (valid service token) | 202 | one entry appended (redacted, best-effort) |
| A logged action's append fails | (n/a to HTTP) | **primary action still succeeds**; failure to app logs/metrics |
| Cross-tenant access blocked elsewhere | (the blocked call's 404/403) | a `cross_tenant_access_blocked` entry appended **in the attempting tenant** |

---

## Role Matrix

| Endpoint | staff | manager | platform_admin | service |
|----------|-------|---------|----------------|---------|
| GET /api/audit-logs | ❌ 403 | ✅ | ❌ 403 | ❌ |
| GET /api/audit-logs/{id} | ❌ 403 | ✅ | ❌ 403 | ❌ |
| GET /api/messages/{id}/audit-logs | ✅* | ✅ | ❌ 403 | ❌ |
| GET /api/escalations/{id}/audit-logs | ❌ 403 | ✅ | ❌ 403 | ❌ |
| POST /api/internal/audit-logs *(optional)* | ❌ 403 | ❌ 403 | ❌ 403 | ✅ |

\* Staff message-scoped read only when `AUDIT_STAFF_MESSAGE_VIEW_ENABLED`; `security`-severity entries are excluded for staff.

---

## Non-Goals (contract-level)

These endpoints never: let a tenant user create/edit/delete an audit entry (append-only); expose another tenant's entries (tenant-scoped, cross-tenant blocked); return secrets, system prompts, JWTs, API keys, full message/reply/document bodies, or any cross-tenant data in `metadata`/`redacted_summary` (redaction); stream/export logs to external systems (no SIEM/CSV/webhook); alert/notify on events; or purge/rotate entries (no retention policy). Writing an audit entry is **best-effort** and never breaks the primary user workflow. Retention, export, alerting, and tamper-proof chaining are **out of scope** for the MVP.
