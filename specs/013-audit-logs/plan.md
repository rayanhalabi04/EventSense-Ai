# Implementation Plan: Audit Logs

**Branch**: `013-audit-logs` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/013-audit-logs/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT; `actor_user_id`; manager (read all) + staff (message-scoped); Platform Admin blocked; login/logout events
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): message ingestion events; `message_id`/`conversation_id`
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): entry point for staff message-scoped view
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): `intent_classified`
- [Spec 007 — Risk Detection](../007-risk-detection/plan.md): `risk_detected`
- [Spec 008 — Document Upload](../008-document-upload/plan.md): `document_uploaded` / `document_processed`
- [Spec 009 — RAG](../009-rag-over-tenant-documents/plan.md): `rag_retrieved` / `rag_no_source_found` / `unsupported_answer_refused`
- [Spec 010 — Suggested Replies](../010-suggested-replies/plan.md): `suggested_reply_*` / `guardrail_refusal`
- [Spec 011 — Follow-Up Tasks](../011-follow-up-tasks/plan.md): `task_*`
- [Spec 012 — Escalation to Manager](../012-escalation-to-manager/plan.md): `escalation_*`

**Note**: This is the final MVP feature. It does not change features 002–012's behavior; it adds an audit logging service that they **call** (one line per meaningful action) plus a tenant-scoped, role-gated read surface and dashboard.

---

## Summary

Add a tenant-scoped, append-only audit log. A new `audit_logs` table stores `tenant_id`, `actor_user_id` (nullable), `actor_type` (`user`/`system`/`ai_service`), `event_type`, `severity` (`info`/`warning`/`error`/`security`), `entity_type`, `entity_id`, `message_id`, `conversation_id`, `metadata` (JSONB), `redacted_summary`, `created_at`, and optional `request_id`. An `AuditService.log_event(...)` function is the single write path: it redacts/validates/size-bounds the payload, stamps `tenant_id` + server `created_at`, and appends — **best-effort** (a failed append is caught and never breaks the caller). Features 002–012 call it at their action completion points (ingest, classify, risk, document, RAG, reply lifecycle, task lifecycle, escalation lifecycle, guardrail refusals, and cross-tenant blocks). Three read endpoints (list with filters, get one, message-scoped list) plus an optional entity-scoped (escalation) list serve a manager dashboard; staff get a message-scoped subset (security entries excluded). Reads are tenant-scoped (404/403, Specs 005–012 pattern), role-gated, paginated, newest-first. Entries are **append-only** — no update/delete path. Metadata never holds secrets, prompts, JWTs, keys, full bodies, or cross-tenant data.

---

## Technical Approach

- **Single write path (`AuditService.log_event`)**: every event is appended through one function so redaction, validation, size-bounding, tenant stamping, and best-effort error handling live in one place. Features pass `event_type`, `actor_type`, `severity`, `entity_type`/`entity_id`, optional `message_id`/`conversation_id`, a small `metadata` dict, and a `redacted_summary`.
- **Best-effort / non-fatal**: `log_event` wraps its own write in a try/except that logs to app logs/metrics and returns; it never raises into the caller (SR-08, FR-014). Writes use an independent transaction/session (or a savepoint) so a logging failure can't roll back the caller's transaction, and a caller's rollback can't silently drop a committed-business + logged pair. (Decision: log **after** the business commit for state-changing events; see research.)
- **Redaction at the boundary**: `log_event` runs a redactor that (a) whitelists/size-bounds metadata keys, (b) strips/ô rejects forbidden keys (token/secret/prompt/password/key), (c) truncates over-cap payloads with `metadata_truncated=true`, and (d) ensures `redacted_summary` is a short non-sensitive sentence (FR-011, FR-012, PR-01..06).
- **Tenant + actor from context only**: `tenant_id` and `actor_user_id` come from the caller's auth/service context, never from client input (SR-01). For `cross_tenant_access_blocked`, the entry is written in the **attempting** tenant with no target fields (SR-07, FR-013).
- **Append-only**: no update/delete service method or endpoint exists; recommend DB-level revocation of UPDATE/DELETE on `audit_logs` (documented), at minimum no code path mutates rows (SR-03, FR-004).
- **Role-gated reads**: manager → tenant-wide list/get/entity-scoped; staff → message-scoped subset (security excluded) when `AUDIT_STAFF_MESSAGE_VIEW_ENABLED`; Platform Admin/unauthenticated blocked (FR-015, SR-04).
- **Closed-but-extensible enums**: `event_type`/`actor_type`/`severity`/`entity_type` are string-backed enums validated at write; new event types need no migration (Decision 8 pattern from Spec 012).

---

## Backend Tasks

1. **`schemas/audit.py`** — Pydantic: `AuditEventInput` (internal write DTO), `AuditLogResponse`, `AuditLogListItem`, `AuditLogListResponse`, `AuditLogFilters`; plus `AuditEventType`, `AuditActorType`, `AuditSeverity`, `AuditEntityType` enums.
2. **`services/audit_service.py`**:
   - `log_event(session, *, tenant_id, actor_user_id, actor_type, event_type, severity, entity_type, entity_id=None, message_id=None, conversation_id=None, metadata=None, summary=None, request_id=None) -> None` — redact + validate + size-bound + stamp + append; **best-effort** (catch-all, never raises).
   - `list_audit_logs(session, tenant_id, filters, *, limit, offset)` — tenant-scoped, filtered (event_type, actor_type/actor_user_id, date range, entity_type/entity_id, message_id, severity), newest-first, paginated.
   - `get_audit_log(session, tenant_id, audit_log_id)` — tenant-resolve (404/403); full entry.
   - `audit_logs_for_message(session, tenant_id, message_id, *, staff_view=False)` — tenant-resolve message; message-scoped entries (exclude `security` when `staff_view`).
   - `audit_logs_for_entity(session, tenant_id, entity_type, entity_id)` — e.g., escalation-scoped (manager).
3. **`services/audit_redaction.py`** — `redact(metadata, summary) -> (clean_metadata, clean_summary, truncated: bool)`; forbidden-key denylist + size cap + summary sanitizer; unit-tested.
4. **Call-site integration (one `log_event` call each)** — wire into existing services:
   - 003 simulator → `message_received` / `message_created_by_simulator`
   - 006 classifier → `intent_classified` (metadata: `predicted_label`, `confidence`, `classification_id`)
   - 007 risk → `risk_detected` (metadata: `risk_level`, short `risk_reason`)
   - 008 documents → `document_uploaded` / `document_processed` (metadata: `document_id`)
   - 009 RAG → `rag_retrieved` / `rag_no_source_found` / `unsupported_answer_refused`
   - 010 replies → `suggested_reply_generated`/`_edited`/`_approved`/`_rejected`; `guardrail_refusal`
   - 011 tasks → `task_created`/`_updated`/`_completed`
   - 012 escalations → `escalation_created`/`_updated`/`_resolved`
   - 002 auth → `user_login` (+ optional `user_logout`)
   - cross-tenant guard (001/shared dependency) → `cross_tenant_access_blocked`
5. **`api/v1/audit_logs.py`** — read endpoints with `require_role` (manager: list/get/entity; staff: message-scoped when enabled) + error→HTTP; optional internal `POST /api/internal/audit-logs` behind service auth.
6. **Config** — `AUDIT_METADATA_MAX_BYTES`, `AUDIT_STAFF_MESSAGE_VIEW_ENABLED`, `AUDIT_LIST_MAX_LIMIT`, `AUDIT_LOG_USER_LOGOUT` in settings.
7. **Router mount** — register the audit-logs router at `/api` in `main.py`.

---

## Database Tasks

1. **Alembic migration** — create `audit_logs`:
   - `id` UUID PK
   - `tenant_id` UUID NOT NULL FK → tenants, indexed
   - `actor_user_id` UUID NULL FK → users
   - `actor_type` VARCHAR(16) NOT NULL (`user`/`system`/`ai_service`)
   - `event_type` VARCHAR(48) NOT NULL
   - `severity` VARCHAR(12) NOT NULL default `info`
   - `entity_type` VARCHAR(32) NULL
   - `entity_id` UUID NULL
   - `message_id` UUID NULL FK → messages (`ON DELETE SET NULL`)
   - `conversation_id` UUID NULL
   - `metadata` JSONB NOT NULL default `{}`
   - `redacted_summary` TEXT NULL
   - `request_id` VARCHAR(64) NULL
   - `created_at` TIMESTAMPTZ NOT NULL default now
2. **Indexes**: `(tenant_id, created_at desc)` (primary list), `(tenant_id, event_type)`, `(tenant_id, severity)`, `(tenant_id, actor_user_id)`, `(tenant_id, message_id)`, `(tenant_id, entity_type, entity_id)`.
3. **SQLAlchemy model** `AuditLog` in `models/audit_log.py` (no `updated_at` — entries are immutable).
4. **Enums** `AuditEventType`/`AuditActorType`/`AuditSeverity`/`AuditEntityType` as constrained strings, validated at the service boundary.
5. **Append-only enforcement** — document/recommend revoking UPDATE/DELETE on `audit_logs` for the app DB role (or a `BEFORE UPDATE/DELETE` trigger that raises). At minimum, no model/service exposes mutation.
6. **No FK cascade that deletes audit rows** — references are loose (`message_id` SET NULL, `entity_id` plain UUID) so deleting a related row never erases history.

---

## Audit Logging Service Tasks

1. **`log_event` contract** — keyword-only, returns `None`, never raises; the one true write path.
2. **Redaction pipeline** — denylist forbidden keys (`*token*`, `*secret*`, `*password*`, `*api_key*`, `*authorization*`, `prompt`, `system_prompt`, `jwt`), drop unknown large blobs, cap to `AUDIT_METADATA_MAX_BYTES`, set `metadata_truncated`, sanitize `redacted_summary` (no body quoting).
3. **Validation** — enum-check `event_type`/`actor_type`/`severity`/`entity_type`; enforce `actor_user_id` present for `actor_type=user` and null otherwise.
4. **Best-effort writer** — isolated session/savepoint; catch all exceptions, log to app logger + increment a metric; never propagate.
5. **Helper shims** — thin convenience wrappers per event family (e.g., `log_intent_classified(...)`) so call sites stay one-liners and consistent.
6. **Cross-tenant logger** — `log_cross_tenant_blocked(attempting_tenant_id, attempting_user_id, attempted_route, attempted_entity_type)` guaranteeing no target-tenant fields.

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/audit-logs` | GET | manager | Tenant-wide list with filters + pagination |
| `/api/audit-logs/{audit_log_id}` | GET | manager | Get one entry (full redacted) |
| `/api/messages/{message_id}/audit-logs` | GET | staff (when enabled), manager | Message-scoped entries (security excluded for staff) |
| `/api/escalations/{escalation_id}/audit-logs` | GET | manager | Escalation-scoped entries |
| `/api/internal/audit-logs` *(optional)* | POST | service auth | Internal/system write (not a tenant user) |

- All resolve tenant first (404/403) per SR-06; `tenant_id`/`actor_user_id` from JWT/service only.
- Filters validated (422 on bad enum/date/pagination); list bounded by `AUDIT_LIST_MAX_LIMIT`, newest-first.
- No update/delete routes exist (append-only); any such method → 405.
- The internal write endpoint, if built, requires a service credential (not a tenant JWT) and runs the same redaction/validation.

---

## Frontend Integration Tasks

1. **`api/auditLogs.ts`** — typed client: `listAuditLogs(filters, page)`, `getAuditLog(id)`, `auditLogsForMessage(messageId)`, `auditLogsForEscalation(escalationId)`.
2. **`types/audit.ts`** — `AuditEventType`, `AuditActorType`, `AuditSeverity`, `AuditEntityType`, `AuditLog` TS types.
3. **`pages/AuditLogsPage.tsx`** — `/audit-logs` manager dashboard; newest-first table with columns (time, event, actor, severity, entity, summary) + filter bar (event_type, actor, date range, entity, severity) + pagination.
4. **`components/audit/AuditLogTable.tsx`** + `AuditLogRow.tsx` — severity badge (info/warning/error/security), actor chip (user name / "System" / "AI service"), entity link (message/escalation/etc.), relative time.
5. **`components/audit/AuditLogDetail.tsx`** — single-entry drawer/modal: full redacted metadata (key/value), all references, severity, actor, timestamp; read-only (no edit/delete controls).
6. **`components/audit/AuditLogFilters.tsx`** — event-type select, actor select, date-range pickers, severity select, entity id input.
7. **Message detail integration (Spec 005)** — optional "Activity" panel showing `auditLogsForMessage` (staff-visible subset) for the open message.
8. **States** — loading, empty, validation errors (422 inline), forbidden (staff tenant-wide / admin), not-found, paginated loading; **no** edit/delete affordances anywhere (append-only).

---

## Testing Tasks

**Backend unit** — `tests/unit/test_audit_redaction.py`: forbidden-key stripping, size cap + `metadata_truncated`, summary sanitization, no-cross-tenant-field guarantee; `tests/unit/test_audit_service.py`: enum validation, actor/`actor_user_id` rule, best-effort (injected failure → no raise), deterministic ordering.

**Backend integration** — `tests/integration/test_audit_logs.py`:
- Pipeline writes (AC-01, AC-02); `rag_no_source_found` warning w/o answer (AC-03); reply/task/escalation events (AC-04)
- Append-only: no mutate path / 405 (AC-05)
- Manager list newest-first + pagination + tenant scope (AC-06); filters (AC-07)
- Get one + cross-tenant 404/403 (AC-08); message-scoped list (AC-09)
- Cross-tenant block entry in attempting tenant, no target data (AC-10); guardrail/unsupported (AC-11)
- Redaction over representative events — no secrets/prompts/JWT/keys/cross-tenant (AC-12); oversized truncation (AC-13)
- Best-effort: injected append failure → primary action still succeeds (AC-14)
- Tenant isolation list/get (AC-15); role enforcement incl. security-manager-only + Platform Admin 403 + 401 (AC-16)
- Server `created_at` + ordering + invalid filter 422 (AC-18)

**Frontend** — render/interaction: dashboard lists tenant entries with filters; severity/actor badges; entry detail shows redacted metadata; no edit/delete controls; staff message-scoped view excludes security (AC-17).

---

## Build Order

1. **DB + model** — Alembic migration + `AuditLog` model + enums; add indexes; document append-only DB grants.
2. **Schemas** — Pydantic DTOs + enums + filter model.
3. **Redaction** — `audit_redaction.redact` (denylist + size cap + summary sanitize) with unit tests.
4. **Service** — `audit_service.log_event` (best-effort, redact/validate/stamp) + read functions (list/get/message/entity) with tenant + role gating; per-family helper shims.
5. **Call-site wiring** — add one `log_event` call in each of 002–012's action points + the cross-tenant guard; verify best-effort isolation.
6. **API** — read endpoints + router mount + role/error mapping; optional internal write endpoint; integration tests.
7. **Frontend** — types + API client → Audit Logs dashboard (table + filters + pagination) → entry detail → message-detail Activity panel → states (no edit/delete).
8. **Validation** — run the 8-step quickstart (message, intent, risk, RAG+reply, task, escalation, cross-tenant, tenant isolation); confirm all 18 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/013-audit-logs/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── audit_logs.py                # read endpoints (+ optional internal write)
│   ├── services/
│   │   ├── audit_service.py             # log_event (best-effort) + list/get/message/entity reads
│   │   └── audit_redaction.py           # redact(): denylist + size cap + summary sanitize
│   ├── models/
│   │   └── audit_log.py                 # AuditLog ORM model (immutable, no updated_at)
│   └── schemas/
│       └── audit.py                     # Pydantic + Audit{EventType,ActorType,Severity,EntityType} enums
├── alembic/versions/
│   └── 00xx_create_audit_logs.py
└── tests/
    ├── integration/
    │   └── test_audit_logs.py
    └── unit/
        ├── test_audit_service.py
        └── test_audit_redaction.py

frontend/
└── src/
    ├── api/
    │   └── auditLogs.ts
    ├── types/
    │   └── audit.ts
    ├── pages/
    │   └── AuditLogsPage.tsx
    └── components/audit/
        ├── AuditLogTable.tsx
        ├── AuditLogRow.tsx
        ├── AuditLogDetail.tsx
        └── AuditLogFilters.tsx
```

Modified files (one `log_event` call each, plus mounts/routes):

```
backend/app/main.py                                  # mount audit-logs router
backend/app/core/config.py                           # AUDIT_* settings
backend/app/services/simulator_service.py            # message_received / message_created_by_simulator
backend/app/services/classifier_service.py (006)     # intent_classified
backend/app/services/risk_service.py (007)           # risk_detected
backend/app/services/document_service.py (008)       # document_uploaded / document_processed
backend/app/services/rag_service.py (009)            # rag_retrieved / rag_no_source_found / unsupported_answer_refused
backend/app/services/reply_service.py (010)          # suggested_reply_* / guardrail_refusal
backend/app/services/task_service.py (011)           # task_*
backend/app/services/escalation_service.py (012)     # escalation_*
backend/app/api/v1/auth.py (002)                     # user_login / user_logout
backend/app/core/tenancy.py (cross-tenant guard)     # cross_tenant_access_blocked
frontend/src/App.tsx                                 # add /audit-logs route
frontend/src/pages/ConversationDetailPage            # optional Activity panel (message-scoped audit)
frontend/src/components/NavBar (or Sidebar)          # add Audit Logs nav item (manager)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–012. The audit log is a cross-cutting concern implemented as a single best-effort `log_event` write path called by existing services, plus a tenant-scoped, role-gated, append-only read surface. The "no edit/delete", "best-effort/non-fatal", and "redaction/no-cross-tenant" guarantees all live in the service + redaction layer so call sites stay one-liners and can't violate them.
