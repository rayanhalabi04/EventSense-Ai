# Implementation Plan: Escalation to Manager

**Branch**: `012-escalation-to-manager` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/012-escalation-to-manager/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT; `staff` (create/view) + `manager` (review/resolve); assignee must be in-tenant manager; Platform Admin blocked
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): the escalated message
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): entry point; replaces the "Escalate" placeholder; shows recommendation
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): `intent_label`
- [Spec 007 — Risk Detection](../007-risk-detection/plan.md): `risk_level` + `risk_reason` + `escalation_recommended`
- [Spec 009 — RAG](../009-rag-over-tenant-documents/plan.md) (optional): source ids
- [Spec 010 — Suggested Replies](../010-suggested-replies/plan.md) (optional): `suggested_reply_id`

**Future integration**: the audit-log feature will log escalation actions. Not implemented here; the model exposes actor + action + timestamps for it.

---

## Summary

Add tenant-scoped escalations that route risky/complex messages to managers. A new `escalations` table snapshots the message's intent (006), risk level + reason (007), RAG source ids (009), suggested reply id (010), and an AI summary, plus `status`, `priority`, `assigned_manager_id`, `manager_notes`, and timestamps. An `EscalationService` enforces tenant ownership (404/403, Specs 005–011 pattern), the role split (staff create/view, manager resolve/assign/notes), in-tenant reference validation (message, reply, manager assignee), and a status state machine (`open → in_review → resolved | cancelled`). Six REST endpoints cover create / list (queue) / get / update / resolve / message-escalations. High-risk messages show an escalation recommendation (from Spec 007), but escalations are **staff-confirmed**, never auto-created or auto-resolved. The feature **sends no client message, does not approve/send the suggested reply, and creates no task**. On creation the related message may become `escalated`.

---

## Technical Approach

- **Staff-confirmed creation**: escalations are created only via an explicit authenticated `POST /api/escalations`. The recommendation is a read-only UI signal (Spec 007 `escalation_recommended`); no code path auto-creates (FR-009, SR-07).
- **Context snapshot at creation**: the service reads intent (006), risk (007), and (if present) RAG sources (009) + suggested reply (010), and stores them on the escalation as a point-in-time snapshot — later upstream changes don't mutate it (SR-08).
- **Role split + in-tenant references**: `staff` create/view; `manager` resolve/cancel/assign/notes. `message_id`, `suggested_reply_id`, and `assigned_manager_id` are resolved within the JWT tenant (and assignee must have role `manager`) before writing (SR-03, SR-04).
- **Status state machine**: `open → in_review → resolved | cancelled`; `open → resolved|cancelled` allowed; terminal states immutable; invalid transitions → 422.
- **Message status side effect**: on create, set the related message's status to `escalated` (non-destructive, isolated).
- **Optional AI summary**: an `EscalationSummarizer` produces `ai_summary` from the captured context; behind an interface with a deterministic stub; failure → escalation still created without summary.
- **No side effects**: no endpoint/method sends a client message, approves/sends a reply (Spec 010), or creates a task (Spec 011) (SR-06).

---

## Backend Tasks

1. **`schemas/escalation.py`** — Pydantic: `EscalationCreateRequest`, `EscalationUpdateRequest`, `EscalationResponse`, `EscalationListItem`, `ResolveRequest` (optional notes), plus `EscalationStatus` and `EscalationPriority` enums.
2. **`services/escalation_service.py`**:
   - `create_escalation(session, tenant_id, user, data)` — resolve message in-tenant; capture intent/risk/sources/reply snapshot; optional `ai_summary`; validate priority + (optional) assignee-manager; store status `open`, `created_by`; set message `escalated` (isolated).
   - `list_escalations(session, tenant_id, filters)` — tenant-scoped queue with status/priority/assignee filters + sensible ordering (urgent/open first).
   - `get_escalation(session, tenant_id, escalation_id)` — tenant-resolve (404/403); full context.
   - `update_escalation(session, tenant_id, user, escalation_id, data)` — manager-only mutations (status/priority/assignee/notes); guard transitions; validate assignee.
   - `resolve_escalation(session, tenant_id, user, escalation_id)` — manager-only; non-terminal → `resolved`, set `resolved_at`.
   - `escalations_for_message(session, tenant_id, message_id)` — tenant-resolve message; return its escalations.
3. **`ai/escalation_summarizer.py`** (optional) — `summarize(context) -> str`; interface + deterministic stub; raises `SummaryUnavailable` (non-fatal).
4. **`api/v1/escalations.py`** — six endpoints with `require_role` (create/view: staff+manager; resolve/update/assign/notes: manager) + error→HTTP + state-machine guards.
5. **Reuse upstream** — read intent (006), risk (007), RAG results (009), suggested reply (010); validate assignee against users (002, role `manager`).
6. **Config** — `ESCALATION_DEFAULT_PRIORITY`, `ESCALATION_SUMMARY_ENABLED` in settings.
7. **Router mount** — register the escalations router at `/api` in `main.py`.

---

## Database Tasks

1. **Alembic migration** — create `escalations`:
   - `id` UUID PK
   - `tenant_id` UUID NOT NULL FK → tenants, indexed
   - `message_id` UUID NOT NULL FK → messages, `ON DELETE CASCADE`, indexed
   - `created_by` UUID NOT NULL FK → users
   - `assigned_manager_id` UUID NULL FK → users
   - `intent_label` VARCHAR(40) NULL (snapshot)
   - `risk_level` VARCHAR(10) NULL (snapshot)
   - `risk_reason` TEXT NULL (snapshot)
   - `ai_summary` TEXT NULL
   - `suggested_reply_id` UUID NULL FK → suggested_replies
   - `source_document_ids` JSONB NOT NULL default `[]`
   - `source_chunk_ids` JSONB NOT NULL default `[]`
   - `status` VARCHAR(20) NOT NULL default `open`
   - `priority` VARCHAR(10) NOT NULL default `medium`
   - `manager_notes` TEXT NULL
   - `created_at`, `updated_at` TIMESTAMPTZ
   - `resolved_at` TIMESTAMPTZ NULL
2. **Indexes**: `(tenant_id, status)`, `(tenant_id, priority)`, `(tenant_id, assigned_manager_id)`, `(tenant_id, message_id)`.
3. **SQLAlchemy model** `Escalation` in `models/escalation.py` with relationships to `Message`, `User` (creator + assignee), `SuggestedReply`.
4. **Enums** `EscalationStatus`/`EscalationPriority` as constrained strings, validated at the boundary.
5. **Message status** — reuse `messages.status`; allow value `escalated` (migration or free string; document choice).

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/escalations` | POST | staff, manager | Create an escalation (staff-confirmed) |
| `/api/escalations` | GET | manager (+ staff view) | Queue: list tenant escalations (filters) |
| `/api/escalations/{escalation_id}` | GET | staff, manager | Get one escalation (full context) |
| `/api/escalations/{escalation_id}` | PATCH | manager | Update status/priority/assignee/notes |
| `/api/escalations/{escalation_id}/resolve` | POST | manager | Resolve (sets resolved_at) |
| `/api/messages/{message_id}/escalations` | GET | staff, manager | List a message's escalations |

- All resolve tenant first (404/403) per SR-05; `tenant_id`/`created_by` from JWT only.
- Assignee validated as in-tenant **manager**; transitions guarded (422); resolve/cancel/notes manager-only (403 for staff).
- Consistent `error_code` payloads (see contracts).

---

## Frontend Integration Tasks

1. **`api/escalations.ts`** — typed client: `createEscalation`, `listEscalations(filters)`, `getEscalation(id)`, `updateEscalation(id, payload)`, `resolveEscalation(id)`, `escalationsForMessage(messageId)`.
2. **`types/escalation.ts`** — `EscalationStatus`, `EscalationPriority`, `Escalation` TS types.
3. **`pages/EscalationsPage.tsx`** — `/escalations` manager queue; lists with status/priority/assignee filters; urgent/open first.
4. **`components/escalations/EscalationList.tsx`** + `EscalationRow.tsx` — priority badge, status badge, intent/risk chips, assignee, related message link, age.
5. **`components/escalations/EscalationDetail.tsx`** — full captured context (message, intent, risk + reason, AI summary, RAG sources, suggested reply link); manager actions: in_review, assign, notes, resolve, cancel.
6. **Detail-page integration (Spec 005)** — replace the "Escalate" placeholder with a real **Escalate** control + an **escalation recommendation** banner when Spec 007 `escalation_recommended` is true; show the message's existing escalations.
7. **States** — loading, empty queue, validation errors (422 inline), forbidden (staff resolve / admin), not-found, summary-unavailable (created without summary), terminal-state (disable edits).

---

## Optional AI Escalation-Recommendation Tasks

1. **Recommendation source** — read Spec 007 `escalation_recommended` + risk level; surface a detail-page banner. Read-only; never creates.
2. **Priority pre-fill** — map risk level → suggested priority (high → high/urgent), staff-overridable in the form.
3. **AI summary** — `EscalationSummarizer` builds `ai_summary` from message + intent + risk + sources + reply; deterministic stub for tests.
4. **No auto-create guarantee** — recommendation/summary endpoints/components create nothing; creation is a separate confirmed POST.
5. **Graceful fallback** — `SummaryUnavailable` → escalation created without summary; feature flag `ESCALATION_SUMMARY_ENABLED`.

---

## Testing Tasks

**Backend integration** — `tests/integration/test_escalations.py`:
- Create + context snapshot (AC-01, AC-02); created without reply/RAG (AC-03)
- Tenant isolation list/get (AC-04, AC-05, AC-07)
- Queue filters (AC-06); update status/priority/assignee/notes + bad assignee (AC-08)
- Resolve + resolved_at; cancel (AC-09); invalid transitions (AC-10)
- Role split: staff resolve → 403 (AC-11)
- Message escalations list (AC-12); no message/reply-approve/task side effects (AC-13)
- Recommendation present + no auto-create (AC-14); Platform Admin 403 (AC-15); message → escalated (AC-16)
- Cross-tenant message rejected + snapshot immutability after re-classify (AC-18)

**Unit** — `tests/unit/test_escalation_service.py`: state machine (valid/invalid transitions), assignee in-tenant-manager validation, snapshot capture, priority-from-risk; `tests/unit/test_escalation_summarizer.py`: deterministic stub + unavailable fallback.

**Frontend** — render/interaction: queue lists tenant escalations; detail shows context; manager resolve/assign/notes; staff cannot resolve; recommendation banner + confirm-to-create (AC-17).

---

## Build Order

1. **DB + model** — Alembic migration + `Escalation` model + enums; confirm `messages.status` supports `escalated`.
2. **Schemas** — Pydantic models + enums.
3. **Service** — `escalation_service` (create with snapshot + message-status; list/get; update; resolve/cancel) with tenant + role + assignee-manager validation + state machine.
4. **Optional summarizer** — `escalation_summarizer` (interface + stub) wired into create (non-fatal).
5. **API** — six endpoints + router mount + error/state/role mapping; integration tests.
6. **Frontend** — types + API client → Escalations queue page → list → detail (manager actions) → detail-page Escalate control + recommendation banner → states.
7. **Validation** — run the 5-scenario quickstart (complaint, cancellation, payment, manager review, tenant isolation); confirm all 18 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/012-escalation-to-manager/
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
│   │   └── escalations.py               # 6 endpoints
│   ├── services/
│   │   └── escalation_service.py        # create / list / get / update / resolve / message-escalations
│   ├── ai/
│   │   └── escalation_summarizer.py     # optional ai_summary (interface + stub)
│   ├── models/
│   │   └── escalation.py                # Escalation ORM model
│   └── schemas/
│       └── escalation.py                # Pydantic + EscalationStatus/EscalationPriority enums
├── alembic/versions/
│   └── 00xx_create_escalations.py
└── tests/
    ├── integration/
    │   └── test_escalations.py
    └── unit/
        ├── test_escalation_service.py
        └── test_escalation_summarizer.py

frontend/
└── src/
    ├── api/
    │   └── escalations.ts
    ├── types/
    │   └── escalation.ts
    ├── pages/
    │   └── EscalationsPage.tsx
    └── components/escalations/
        ├── EscalationList.tsx
        ├── EscalationRow.tsx
        └── EscalationDetail.tsx
```

Modified files:

```
backend/app/main.py                          # mount escalations router
backend/app/core/config.py                   # ESCALATION_* settings
backend/app/services/<message status owner>  # allow messages.status = escalated
frontend/src/App.tsx                         # add /escalations route
frontend/src/pages/ConversationDetailPage    # replace "Escalate" placeholder + recommendation banner + message escalations
frontend/src/components/NavBar (or Sidebar)  # add Escalations nav item (manager)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–011. Escalation creation is a deliberate, staff-confirmed `POST`; the recommendation/summarizer in `backend/app/ai/` are strictly read-only/non-fatal, keeping the "no auto-create / no auto-resolve / no send / no reply-approval / no task" guarantees in the service layer.
