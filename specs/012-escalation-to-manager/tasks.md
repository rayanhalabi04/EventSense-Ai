---
description: "Task list for Escalation to Manager feature implementation"
---

# Tasks: Escalation to Manager

**Branch**: `012-escalation-to-manager` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/012-escalation-to-manager/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `tenants` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping, `get_current_tenant_context`
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin` roles; `require_role`; Platform Admin block; `users` table + role (for `created_by` + in-tenant **manager** assignee validation)
- Spec 003 — Message Simulator: `messages` table + `status` field; the escalated message
- Spec 005 — Message Detail Page: conversation/message detail page with the "Escalate" placeholder this feature replaces
- Spec 006 — Intent Classifier: `classification_results` (intent label) — snapshot source
- Spec 007 — Risk Detection: `risk_assessments` (`risk_level`, `risk_reason`, `escalation_recommended`) — snapshot source + recommendation
- Spec 009 — RAG Over Tenant Documents (optional): `rag_queries`/`rag_retrieval_results` — snapshot `source_document_ids`/`source_chunk_ids`
- Spec 010 — Suggested Replies (optional): `suggested_replies` — `suggested_reply_id` link (independent lifecycle)

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `escalations` + one Alembic migration. `EscalationStatus`/`EscalationPriority` persisted as constrained strings (VARCHAR + app-boundary validation), not native PG enums (consistent with Specs 008–011). Source id lists stored as JSONB. The related `messages.status` may gain an `escalated` value (migration or free-string, per the project's message-status model).

**Config defaults** (research.md Decisions 9 & 10): `ESCALATION_DEFAULT_PRIORITY="medium"`, `ESCALATION_SUMMARY_ENABLED=true`; queue ordering `priority desc (urgent→high→medium), status (open/in_review first), created_at asc`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US4]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–011 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant`/`tenants` (Spec 001), `User` + role enum + an "is user a manager in tenant" lookup (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `Message`/`messages` + `status` (Spec 003), `ClassificationResult` reader (Spec 006), `RiskAssessment` reader + `escalation_recommended` (Spec 007), RAG result reader (Spec 009, optional), `SuggestedReply` + latest-reply reader (Spec 010, optional), `NotFoundError`/`ForbiddenError` + their error→HTTP mapping (Spec 001), and the shared `error_code` envelope. Do NOT redefine any of these.
- [ ] T002 Add `ESCALATION_DEFAULT_PRIORITY` (`"medium"`) and `ESCALATION_SUMMARY_ENABLED` (true) to `backend/app/core/config.py` with documented defaults (research.md)
- [ ] T003 Determine and document the `messages.status` model: constrained enum (Spec 003/005) or free string? Record whether the migration must add an `escalated` allowed value or whether no DB change is needed (data-model.md "Message status note"; consistent with Spec 011's `task_created`)
- [ ] T004 Record the exact upstream accessor signatures the snapshot will call — intent (006), risk (007), latest RAG result (009, optional), latest suggested reply (010, optional) — all tenant-scoped, all read-only; confirm they degrade gracefully when 009/010 outputs are absent (FR-002, AC-03)
- [ ] T005 Verify `backend/tests/unit/` and `backend/tests/integration/` exist with `__init__.py`; create any that are missing

**Checkpoint**: Dependencies confirmed reused; config in place; message-status approach + snapshot accessors decided.

---

## Phase 2: Database & Model (Foundational — Blocking)

**Purpose**: The `escalations` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–8 cannot run without this phase.

- [ ] T006 [P] Create the `EscalationStatus` (`open`, `in_review`, `resolved`, `cancelled`) and `EscalationPriority` (`medium`, `high`, `urgent`) string enums in `backend/app/schemas/escalation.py` (shared by service + API layers) — per data-model.md
- [ ] T007 Create the `Escalation` SQLAlchemy model in `backend/app/models/escalation.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `message_id` UUID FK→`messages.id` `ON DELETE CASCADE` NOT NULL indexed; `created_by` UUID FK→`users.id` NOT NULL; `assigned_manager_id` UUID FK→`users.id` NULL; `intent_label` VARCHAR(40) NULL; `risk_level` VARCHAR(10) NULL; `risk_reason` TEXT NULL; `ai_summary` TEXT NULL; `suggested_reply_id` UUID FK→`suggested_replies.id` NULL; `source_document_ids` JSONB NOT NULL default `list`; `source_chunk_ids` JSONB NOT NULL default `list`; `status` VARCHAR(20) NOT NULL default `open`; `priority` VARCHAR(10) NOT NULL default `medium`; `manager_notes` TEXT NULL; `created_at`/`updated_at` TIMESTAMPTZ (server_default now, updated_at onupdate now); `resolved_at` TIMESTAMPTZ NULL; `message` + `creator`(foreign_keys=[created_by]) + `assignee`(foreign_keys=[assigned_manager_id]) + `suggested_reply` relationships; `Index("ix_esc_tenant_status", "tenant_id", "status")`, `Index("ix_esc_tenant_priority", "tenant_id", "priority")`, `Index("ix_esc_tenant_assignee", "tenant_id", "assigned_manager_id")`, `Index("ix_esc_tenant_message", "tenant_id", "message_id")` — per data-model.md (depends on T006)
- [ ] T008 Create Alembic migration `backend/alembic/versions/00xx_create_escalations.py`: create `escalations` with all columns, the FKs (`tenant_id`→`tenants.id`, `message_id`→`messages.id` ON DELETE CASCADE, `created_by`→`users.id`, `assigned_manager_id`→`users.id`, `suggested_reply_id`→`suggested_replies.id`), defaults (`status='open'`, `priority='medium'`, JSONB `[]` for source id lists), and the four composite indexes; **if** `messages.status` is a constrained enum (per T003), add the `escalated` allowed value here (non-destructive); provide a correct `downgrade()` dropping the table + indexes (and reverting the enum value if added) (depends on T007, T003)

**Checkpoint**: `alembic upgrade head` creates the table; ORM model importable; `messages.status` accepts `escalated`.

---

## Phase 3: Schemas (Foundational — Blocking)

**Purpose**: Pydantic request/response models shared by the service and endpoints. The queue item is a metadata summary; the full response carries the captured context.

- [ ] T009 Add Pydantic models to `backend/app/schemas/escalation.py` (alongside the enums from T006) per data-model.md: `EscalationCreateRequest` (`message_id: UUID`, `priority: EscalationPriority | None = None`, `reason: str | None = None`, `assigned_manager_id: UUID | None = None`), `EscalationUpdateRequest` (all optional: `status`, `priority`, `assigned_manager_id`, `manager_notes` (≤4000)), `ResolveRequest` (`manager_notes: str | None = None` (≤4000)), `EscalationListItem` (`id`, `message_id`, `status`, `priority`, `intent_label`, `risk_level`, `assigned_manager_id`, `created_by`, `created_at`, `updated_at`, `resolved_at`; `from_attributes=True`), `EscalationResponse(EscalationListItem)` (adds `tenant_id`, `risk_reason`, `ai_summary`, `suggested_reply_id`, `source_document_ids: list[UUID]`, `source_chunk_ids: list[UUID]`, `manager_notes`), `EscalationListResponse` (`items: list[EscalationListItem]`, `total: int`), `MessageEscalationsResponse` (`message_id: UUID`, `items: list[EscalationListItem]`, `total: int`)

**Checkpoint**: Schemas importable — service phase can begin.

---

## Phase 4: Escalation Service (Foundational — Blocking)

**Purpose**: Tenant ownership resolution, the context snapshot at creation, in-tenant reference validation (message + reply + manager assignee), the role split (staff create/view, manager mutate), the status state machine, the `escalated` message side effect, and the no-side-effects guarantee. **BLOCKS the API in Phase 5.**

- [ ] T010 Define typed errors in `backend/app/services/escalation_service.py` (or the shared errors module): `InvalidAssignee` (→422 `INVALID_ASSIGNEE`), `InvalidStateTransition` (→422 `INVALID_STATE_TRANSITION`); reuse `NotFoundError`/`ForbiddenError` (Spec 001) for 404/403 and the existing role-guard 403 `INSUFFICIENT_ROLE` (data-model.md error→HTTP mapping)
- [ ] T011 Implement `_resolve_message_or_raise(session, tenant_id, message_id)` and `get_escalation(session, tenant_id, escalation_id)` in `backend/app/services/escalation_service.py`: load the row, `NotFoundError` (404) if absent, `ForbiddenError` (403) if in another tenant — mirroring Specs 005–011 SR-05 (depends on T007)
- [ ] T012 Implement `_assert_in_tenant_manager(session, tenant_id, user_id)` in `backend/app/services/escalation_service.py`: raise `InvalidAssignee` (422) if the user does not exist, is not in the caller's tenant, or does not have role `manager` (SR-03, FR-004) (depends on T010)
- [ ] T013 Implement `_require_manager(user)` in `backend/app/services/escalation_service.py`: raise the role-guard 403 `INSUFFICIENT_ROLE` when a `staff` user attempts a manager-only mutation (resolve/cancel/assign/notes/status) (SR-04, FR-015) (depends on T010)
- [ ] T014 Implement `_assert_not_terminal(esc)`, `_apply_transition(esc, new_status)`, and `_priority_from_risk(risk)` in `backend/app/services/escalation_service.py`: terminal = `status ∈ {resolved, cancelled}` → `InvalidStateTransition`; `_apply_transition` enforces allowed moves (`open → in_review|resolved|cancelled`, `in_review → resolved|cancelled`) and sets `resolved_at` when moving to `resolved` (no auto-resolve); `_priority_from_risk` maps risk level → default priority (high risk → `high`/`urgent`, else `medium`/`ESCALATION_DEFAULT_PRIORITY`) (data-model.md state machine; research.md Decision 9; FR-008) (depends on T010)
- [ ] T015 Implement `_mark_message_escalated(session, message)` in `backend/app/services/escalation_service.py`: set the related message's status to `escalated` (non-destructive); **isolated** so a failure here never fails escalation creation (FR-014, research.md Decision 6) (depends on T007)
- [ ] T016 [US1] Implement `create_escalation(session, tenant_id, user, data: EscalationCreateRequest) -> Escalation` in `backend/app/services/escalation_service.py`: resolve message (404/403); read snapshot sources — intent (006), risk (007), latest RAG (009, optional), latest reply (010, optional) — via T004 accessors; if `assigned_manager_id` set, `_assert_in_tenant_manager` (422 `INVALID_ASSIGNEE`); `priority = (data.priority or _priority_from_risk(risk))`; optionally build `ai_summary` (T021, non-fatal); build `Escalation` capturing `intent_label`, `risk_level`, `risk_reason`, `suggested_reply_id`, `source_document_ids`/`source_chunk_ids` (empty when RAG absent), `status=open`, `created_by=user.id`; flush; `_mark_message_escalated`; commit (transactional — no partial escalation on failure). **Sends no client message, does not approve/send the reply, creates no task** (FR-001..FR-003, FR-010..FR-012, FR-016, AC-01..AC-03, AC-13, AC-16) (depends on T011, T012, T014, T015)
- [ ] T017 [US2] Implement `list_escalations(session, tenant_id, *, status=None, priority=None, assigned_manager_id=None) -> (items, total)` in `backend/app/services/escalation_service.py`: `WHERE tenant_id` (SR-02) + optional filters; order by priority rank desc (urgent→high→medium), then open/in_review first, then `created_at asc` (FR-005, AC-05, AC-06; research.md Decision 9) (depends on T007)
- [ ] T018 [US2][US3] Implement `update_escalation(session, tenant_id, user, escalation_id, data: EscalationUpdateRequest) -> Escalation` in `backend/app/services/escalation_service.py`: `_require_manager` (403 for staff); `get_escalation` (404/403); `_assert_not_terminal`; if `assigned_manager_id` set, `_assert_in_tenant_manager` then assign; apply non-null `priority`/`manager_notes`; if `status` set, `_apply_transition` (guards + `resolved_at`); commit; `updated_at` refreshes (FR-006, FR-015, AC-08, AC-10, AC-11) (depends on T011, T012, T013, T014)
- [ ] T019 [US3] Implement `resolve_escalation(session, tenant_id, user, escalation_id, notes=None) -> Escalation` in `backend/app/services/escalation_service.py`: `_require_manager` (403 for staff); `get_escalation` (404/403); `_assert_not_terminal`; store optional `manager_notes`; set status `resolved`, `resolved_at=now`; commit (FR-007, FR-015, AC-09, AC-11) (depends on T011, T013, T014)
- [ ] T020 [US2] Implement `escalations_for_message(session, tenant_id, message_id) -> (items, total)` in `backend/app/services/escalation_service.py`: resolve message (404/403); return escalations `WHERE tenant_id AND message_id ORDER BY created_at DESC` (FR-013, AC-12) (depends on T011)

**Checkpoint**: Service complete; tenant scoping, context snapshot, in-tenant reference validation, role split, state machine, and the isolated `escalated` side effect all enforced; no send/reply-approval/task anywhere.

---

## Phase 5: API Endpoints (User Stories 1–3)

**Purpose**: Expose the six endpoints with the role matrix (create/view: staff+manager; mutate/resolve: manager) and error→HTTP mapping. `tenant_id` and `created_by` are always derived from the JWT; any client-supplied tenant is ignored. **🎯 MVP backend deliverable. No send/reply-approval/task endpoint exists.**

- [ ] T021 [US1] Implement `POST /api/escalations` in `backend/app/api/v1/escalations.py`: `require_role("staff", "manager")`; validate `EscalationCreateRequest`; call `service.create_escalation`; return `EscalationResponse` **201**. Map `NotFoundError`→404 `MESSAGE_NOT_FOUND`, `ForbiddenError`→403 `CROSS_TENANT_FORBIDDEN`, `InvalidAssignee`→422 `INVALID_ASSIGNEE`, invalid priority→422 (contracts §1, AC-01, AC-02, AC-18) (depends on T016)
- [ ] T022 [US2] Implement `GET /api/escalations` in `backend/app/api/v1/escalations.py`: `require_role("staff", "manager")`; parse `status`/`priority`/`assigned_manager_id` query params; call `service.list_escalations`; return `EscalationListResponse` (200); invalid filter value → 422 (contracts §2, AC-05, AC-06) (depends on T017)
- [ ] T023 [US2] Implement `GET /api/escalations/{escalation_id}` in `backend/app/api/v1/escalations.py`: `require_role("staff", "manager")`; call `service.get_escalation`; return full `EscalationResponse` (200); missing → 404 `ESCALATION_NOT_FOUND`, cross-tenant → 403 `CROSS_TENANT_FORBIDDEN` (contracts §3, AC-07) (depends on T011)
- [ ] T024 [US2][US3] Implement `PATCH /api/escalations/{escalation_id}` in `backend/app/api/v1/escalations.py`: `require_role("manager")` (staff → 403 `INSUFFICIENT_ROLE`); validate `EscalationUpdateRequest`; call `service.update_escalation`; return updated `EscalationResponse` (200); terminal/illegal transition → 422 `INVALID_STATE_TRANSITION`, cross-tenant/non-manager assignee → 422 `INVALID_ASSIGNEE` (contracts §4, AC-08, AC-10, AC-11) (depends on T018)
- [ ] T025 [US3] Implement `POST /api/escalations/{escalation_id}/resolve` in `backend/app/api/v1/escalations.py`: `require_role("manager")` (staff → 403); optional `ResolveRequest` (manager_notes); call `service.resolve_escalation`; return `EscalationResponse` (200) with `resolved_at`; terminal → 422 `INVALID_STATE_TRANSITION` (contracts §5, AC-09, AC-11) (depends on T019)
- [ ] T026 [US2] Implement `GET /api/messages/{message_id}/escalations` in `backend/app/api/v1/escalations.py`: `require_role("staff", "manager")`; call `service.escalations_for_message`; return `MessageEscalationsResponse` (`message_id`, `items`, `total`) (200); cross-tenant → 404/403 (contracts §6, AC-12) (depends on T020)
- [ ] T027 Mount the escalations router at `/api` in `backend/app/main.py` so all routes resolve (plan.md Backend Tasks #7) (depends on T021–T026)
- [ ] T028 [US2] Surface message escalations + the recommendation flag to the detail page: extend `backend/app/services/conversation_service.py` (or expose the dedicated `GET .../escalations` fetch) so the Spec 005 detail response can carry the message's existing escalations and the Spec 007 `escalation_recommended` flag (plan.md Modified files, FR-009, FR-013) (depends on T020)

**Checkpoint**: All six endpoints return per the contract; role matrix (manager-only mutate) + tenant resolution + state machine enforced. Backend MVP complete.

---

## Phase 6: Optional AI Summary & Recommendation (User Story 4 — P2, read-only/non-fatal)

**Purpose**: An optional `ai_summary` (non-fatal) and the high-risk escalation **recommendation** (read-only, from Spec 007). Neither auto-creates an escalation. Gated by `ESCALATION_SUMMARY_ENABLED`.

- [ ] T029 [US4] Implement the `EscalationSummarizer` interface in `backend/app/ai/escalation_summarizer.py`: `summarize(message, classification, risk, rag, reply) -> str`; a heuristic/LLM impl plus a **deterministic stub** for tests; raise typed `SummaryUnavailable` on failure (research.md Decision 10)
- [ ] T030 [US4] Wire the summarizer into `create_escalation` (T016) **non-fatally**, gated by `ESCALATION_SUMMARY_ENABLED`: on `SummaryUnavailable` (or flag off) the escalation is still created with `ai_summary=None` — summary never blocks creation (FR-002 optional, research.md Decision 10) (depends on T016, T029)
- [ ] T031 [US4] Ensure the recommendation is read-only and never auto-creates: confirm the Spec 007 `escalation_recommended` flag is surfaced (via T028) as a display signal only; there is **no** code path that creates an escalation without an explicit `POST /api/escalations` (FR-009, SR-07, AC-14) (depends on T028)

**Checkpoint**: `ai_summary` is captured when available and skipped on failure (creation never blocked); the recommendation is a read-only signal that creates nothing.

---

## Phase 7: Frontend Integration (User Stories 1–4)

**Purpose**: Add an Escalations queue page (manager-primary), an escalation detail view with manager actions, and replace the Spec 005 "Escalate" placeholder with a real control + a high-risk recommendation banner.

- [ ] T032 [P] Add TS types to `frontend/src/types/escalation.ts`: `EscalationStatus`, `EscalationPriority`, `Escalation` (data-model.md Frontend Types)
- [ ] T033 [P] Add the typed API client `frontend/src/api/escalations.ts`: `createEscalation(payload)`, `listEscalations(filters)`, `getEscalation(id)`, `updateEscalation(id, payload)`, `resolveEscalation(id, notes?)`, `escalationsForMessage(messageId)` — calling the endpoints with the auth header (depends on T032)
- [ ] T034 [P] Implement status/priority badge components in `frontend/src/components/escalations/` (e.g. `EscalationStatusBadge.tsx`, `EscalationPriorityBadge.tsx`): colored badges for each `EscalationStatus`/`EscalationPriority` value (AC-17) (depends on T032)
- [ ] T035 Implement `frontend/src/components/escalations/EscalationRow.tsx` + `EscalationList.tsx`: a row/table showing priority badge, status badge, intent/risk chips, assignee, related message link, age; empty state (plan.md Frontend #4, AC-17) (depends on T033, T034)
- [ ] T036 Implement `frontend/src/components/escalations/EscalationDetail.tsx`: full captured context (message, intent, risk + reason, AI summary, RAG source ids, linked suggested reply); manager actions — move to `in_review`, assign (in-tenant manager selector), add `manager_notes`, resolve, cancel (via PATCH `status=cancelled`); actions disabled for terminal escalations and **hidden/disabled for staff** (read + create only) (plan.md Frontend #5, AC-08, AC-09, AC-10, AC-11, AC-17) (depends on T033, T034)
- [ ] T037 Implement `frontend/src/pages/EscalationsPage.tsx` at route `/escalations`: manager queue listing tenant escalations via `EscalationList` (urgent/open first) with status/priority/assignee filters; loading/empty/error states; register the route in `frontend/src/App.tsx` and add an Escalations nav item (manager-primary) (plan.md Frontend #3, AC-05, AC-17) (depends on T035)
- [ ] T038 [US1][US4] Replace the Spec 005 "Escalate" placeholder in `frontend/src/pages/ConversationDetailPage`: an **Escalate** control opening a form pre-filled with priority from risk; a **high-risk escalation recommendation banner** shown when Spec 007 `escalation_recommended` is true (recommendation only — escalation created on explicit confirm, never auto); show the message's existing escalations (via `escalationsForMessage`); leave any "Create Task" control (Spec 011) independent (plan.md Frontend #6, FR-009, AC-14, AC-17) (depends on T033, T035)

**Checkpoint**: Manager queue lists tenant escalations with badges/filters; detail shows full context with manager-only actions; the message detail page can escalate and shows the recommendation banner; terminal escalations are read-only; staff see read+create only.

---

## Phase 8: Frontend Tests

**Purpose**: Render/interaction tests for the queue, detail, create flow, recommendation banner, and resolve action.

- [ ] T039 [P] `EscalationList`/`EscalationsPage` render tests in `frontend/src/components/escalations/__tests__/EscalationList.test.tsx`: renders tenant escalations with priority + status badges, intent/risk chips, assignee; empty + loading + error states render (AC-17)
- [ ] T040 [P] `EscalationDetail` test: renders full captured context; manager Resolve calls `resolveEscalation` and reflects `resolved`; manager notes update reflects in the UI; resolve/assign/notes controls hidden/disabled for a staff user and for terminal escalations (AC-09, AC-11, AC-17) (depends on T036)
- [ ] T041 [P] Message-detail escalation test: the Escalate control creates an escalation on confirm; the high-risk recommendation banner appears **as a recommendation only** (no escalation without the explicit create call); forbidden/error/loading states render (AC-14, AC-17) (depends on T038)

**Checkpoint**: Frontend states + interactions verified; recommendation-only behaviour confirmed.

---

## Phase 9: Tenant Isolation & Role Security Tests (cross-cutting)

**Purpose**: Prove Tenant A never accesses Tenant B escalations/messages/assignees/replies, `tenant_id`/`created_by` come only from the JWT, and the role split holds. `backend/tests/integration/test_escalations.py`.

- [ ] T042 [P] Staff creates an own-tenant escalation from a message → 201, escalation `tenant_id` = caller's tenant, `created_by` = caller, linked to the message, status `open` (AC-01); manager can also create (role matrix)
- [ ] T043 [P] Tenant isolation on queue: escalations created in A and B → listing as A returns only A's (B absent) (AC-04, AC-05)
- [ ] T044 [P] Tenant A cannot read/update/resolve a Tenant B escalation: `GET`/`PATCH`/`POST .../resolve` on a B escalation as A → 403 `CROSS_TENANT_FORBIDDEN` (or 404), no change (AC-07, SR-02)
- [ ] T045 [P] Tenant A cannot create an escalation for a Tenant B message: `message_id` of a B message → 404/403; nothing stored (AC-18, SR-03)
- [ ] T046 [P] Cross-tenant / non-manager assignee rejected: `assigned_manager_id` from another tenant, or an in-tenant **staff** user, → 422 `INVALID_ASSIGNEE`; nothing stored/changed (AC-08, SR-03); cross-tenant `suggested_reply_id` rejected (422/403)
- [ ] T047 [P] Role split: a `staff` user calling `PATCH /api/escalations/{id}` or `POST .../resolve` → 403 `INSUFFICIENT_ROLE`; staff can `POST /api/escalations` and `GET` (create + view only) (AC-11, SR-04, FR-015)
- [ ] T048 [P] Client-supplied `tenant_id`/`created_by` ignored: values injected into the body do not change ownership — escalation scopes to the JWT tenant and `created_by` is the JWT user (SR-01, SR-08)
- [ ] T049 [P] Platform Admin → 403 `INSUFFICIENT_ROLE` on **all** escalation endpoints (create, list, get, patch, resolve, message-escalations) (AC-15, SR-04); unauthenticated → 401 on each

**Checkpoint**: Tenant isolation and the role split are proven; no cross-tenant access; no client-spoofable ownership; staff cannot mutate/resolve.

---

## Phase 10: Escalation Behaviour & Integration Tests

**Purpose**: Verify creation + context snapshot, snapshot immutability, the state machine, resolve/cancel, no-side-effects, the message side effect, and the optional summary/recommendation. `backend/tests/integration/test_escalations.py` + `backend/tests/unit/`.

- [ ] T050 [P] Unit `backend/tests/unit/test_escalation_service.py`: state machine valid transitions (`open→in_review→resolved`, `open→cancelled`, `in_review→cancelled`) and invalid ones (edit/resolve/cancel a terminal escalation → `InvalidStateTransition`); `_assert_in_tenant_manager` rejects out-of-tenant and non-manager; `_priority_from_risk` mapping; `resolved_at` set only on resolve (FR-008, AC-10)
- [ ] T051 [P] Unit `backend/tests/unit/test_escalation_summarizer.py`: deterministic stub output; `SummaryUnavailable` propagates and is handled non-fatally by the service (research.md Decision 10) (depends on T029)
- [ ] T052 [P] Create captures the context snapshot: `intent_label` (006), `risk_level`+`risk_reason` (007), `source_document_ids`/`source_chunk_ids` (009 when available), `suggested_reply_id` (010 when available), `ai_summary` (when enabled); all stored fields per FR-003 (AC-01, AC-02)
- [ ] T053 [P] Escalation created even when RAG/reply absent: a message with no RAG and no reply → escalation created with empty source id lists and null `suggested_reply_id`/`ai_summary` (AC-03, FR-002)
- [ ] T054 [P] Snapshot immutability: after creating an escalation, re-classifying/re-running risk on the message does **not** mutate the escalation's captured `intent_label`/`risk_level`/`risk_reason`/`ai_summary`/source ids (AC-18, SR-08)
- [ ] T055 [P] Queue filters by `status`, `priority`, `assigned_manager_id` return correct in-tenant subsets; ordering is urgent/open first (AC-06; research.md Decision 9)
- [ ] T056 [P] Manager update persists status/priority/assignee/notes and refreshes `updated_at`; assign to an in-tenant manager updates `assigned_manager_id` (AC-08)
- [ ] T057 [P] Resolve sets status `resolved` + `resolved_at` (AC-09); cancel via PATCH `status=cancelled` sets `cancelled` (AC-09); resolved/cancelled escalations remain listed and filterable (US3)
- [ ] T058 [P] Invalid transitions rejected: edit/resolve/cancel a `resolved` or `cancelled` escalation → 422 `INVALID_STATE_TRANSITION`; resolving an already-resolved one → 422 (AC-10)
- [ ] T059 [P] `GET /api/messages/{id}/escalations` returns the message's tenant-scoped escalations; cross-tenant message → 404/403; a message may have multiple escalations (duplicates allowed) (AC-12; research.md Decision 12)
- [ ] T060 [P] No side effects: creating/updating/resolving an escalation sends **no client message**, does **not** approve/send the Spec 010 suggested reply (the linked reply stays in its own un-approved state), and creates **no** Spec 011 task — assert no such records/effects exist (AC-13, FR-010, FR-011, FR-012, SR-06)
- [ ] T061 [P] On creation, the related message's status becomes `escalated`; creating a second escalation from the same message still succeeds (AC-16, FR-014)
- [ ] T062 [P] No auto-create / no auto-resolve: there is no code path that creates an escalation without an explicit `POST` or resolves one without a manager action; the high-risk recommendation is read-only (AC-14, SR-07) (depends on T031)

**Checkpoint**: All 18 acceptance criteria covered by tests; snapshot capture/immutability, state machine, role split, no-side-effects, message side effect, and the optional summary/recommendation verified.

---

## Phase 11: Quickstart & Manual Validation

**Purpose**: Execute the five-scenario quickstart end to end (quickstart.md). Requires staff + manager accounts per tenant.

- [ ] T063 Run migrations (`alembic upgrade head`); confirm `escalations` created and `messages.status` accepts `escalated`; log in as staff + manager of both demo tenants
- [ ] T064 Scenario 1 — high-risk complaint ("very unhappy ... wedding next week") → staff escalates (high); confirm `status:open`, `intent_label:complaint`, `risk_level:high`, a `risk_reason`, captured `suggested_reply_id` if a reply exists; `GET /messages/{id}/escalations` shows it; message marked `escalated`
- [ ] T065 Scenario 2 — cancellation request → staff escalates **before replying**; confirm `suggested_reply_id` is captured but the reply stays un-approved (escalation does not approve/send it); RAG source ids captured if retrieval ran
- [ ] T066 Scenario 3 — payment issue ("I paid the deposit but no one confirmed.") → staff escalates (medium); confirm intent `payment_issue`; confirm **no task** is created by this feature
- [ ] T067 Scenario 4 — manager review flow: manager lists the queue (urgent/open first); PATCH an open escalation to `in_review` with notes; `POST .../resolve` with notes → `resolved` + `resolved_at`; resolving again → 422 `INVALID_STATE_TRANSITION`; a **staff** resolve attempt → 403 `INSUFFICIENT_ROLE`
- [ ] T068 Scenario 5 — tenant isolation: create an escalation in Royal Events; as Elegant Weddings manager, the RE escalation is absent from the queue and `GET` by id → 403 `CROSS_TENANT_FORBIDDEN`; assigning an RE manager to an EW escalation → 422 `INVALID_ASSIGNEE`
- [ ] T069 Role + no-side-effect checks: Platform Admin `GET /api/escalations` → `INSUFFICIENT_ROLE`; non-existent related message → 404; confirm creating/resolving an escalation sends no client message, does not approve/send the reply, and creates no task; verify the UI queue page, message-detail Escalate control, and recommendation banner

**Checkpoint**: Quickstart passes end to end; creation, snapshot, manager review/resolve, role split, and tenant isolation demonstrated live.

---

## Phase 12: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T070 Verify AC-01..AC-18 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T071 Walk `checklists/requirements.md` Functional / Escalation Workflow / Optional AI Recommendation / Manager Review / Security / Tenant Isolation / API / Data / Testing sections and tick each implemented item
- [ ] T072 Confirm Out-of-Scope items remain **unbuilt**: no sending of any client message, no approving/sending the suggested reply (Spec 010 lifecycle independent), no follow-up task creation (Spec 011 separate), no auto-creation of escalations (staff confirmation required), no auto-resolution (manager action only), no audit-log persistence/API/UI (future integration only), no notifications/paging/email, no SLA timers/timeout auto-escalation, no cross-tenant/shared escalations, no full CRM, no real WhatsApp API/calendar syncing (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 012 verified against spec + checklist; the MVP triage loop closes — risky cases reach a manager with full evidence, with the three hard guarantees (no auto-create, no auto-resolve, no side effects) proven.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (DB/model)** → depends on Phase 1 (incl. the T003 message-status decision); **BLOCKS everything**.
- **Phase 3 (Schemas)** → depends on T006; blocks service + API.
- **Phase 4 (Service)** → depends on Phases 2–3 (and the T004 snapshot accessors); blocks the API.
- **Phase 5 (API)** → depends on Phase 4; **MVP backend deliverable**.
- **Phase 6 (Optional summary/recommendation)** → depends on Phase 5 (T028 surfaces the recommendation; T030 wires the summarizer into create); non-fatal/read-only; can be deferred without blocking the MVP.
- **Phase 7 (Frontend)** → depends on Phase 5 (consumes the endpoints); the recommendation banner also needs Phase 6 (T028/T031).
- **Phase 8 (Frontend tests)** → depends on Phase 7.
- **Phase 9 (Isolation/role tests)** + **Phase 10 (Behaviour tests)** → depend on Phase 5 (Phase 10's summary/recommendation tests need Phase 6).
- **Phase 11 (Quickstart)** → depends on Phases 5–7.
- **Phase 12 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3 — create, queue, review/resolve)

1. Phase 1: Setup (config + message-status decision + snapshot accessors)
2. Phase 2: DB + model + migration (**CRITICAL**)
3. Phase 3: Schemas
4. Phase 4: Service (tenant resolution → context snapshot → in-tenant reference validation → role split → state machine → isolated `escalated` side effect)
5. Phase 5: API (six endpoints + router mount + error/state/role mapping)
6. **STOP and VALIDATE**: run isolation + behaviour tests; confirm tenant scoping, snapshot capture/immutability, role split (staff can't mutate/resolve), state machine, no send/reply-approval/task, `escalated`, client-tenant override ignored
7. Phase 9 + 10: full isolation + behaviour coverage (AC-01..AC-18, minus the optional summary/recommendation AC-14 nuance until Phase 6)

### Incremental Delivery

1. Setup + DB + schemas + service → foundation ready
2. US1 (staff escalate from message + context snapshot) → risky cases become manager cases (**creation MVP**)
3. US2 (manager queue: list/get/filter + message-escalations) → the review surface
4. US3 (manager update/resolve/cancel + state machine) → the case lifecycle closes
5. US4 (optional AI summary + read-only recommendation) → faster, more consistent triage (additive, P2)
6. Frontend → Escalations queue + badges + detail (manager actions) + message-detail Escalate control + recommendation banner
7. Tests + quickstart + acceptance → all 18 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id` and `created_by` are **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SR-01, SR-08); any `tenant_id`/`created_by` in the body/query is ignored (T048)
- **No auto-create** — the high-risk escalation recommendation is read-only (from Spec 007 `escalation_recommended`); escalation creation is a separate explicit staff-confirmed `POST /api/escalations` (FR-009, SR-07, research.md Decision 1, T031, T062). First hard guarantee
- **No auto-resolve** — resolution is a manager-only action; there is no timer/auto-resolve path (SR-07, T062). Second hard guarantee
- **No side effects** — no endpoint or service method sends a client message, approves/sends the Spec 010 suggested reply (it only links `suggested_reply_id`; the reply's lifecycle stays independent), or creates a Spec 011 task; the only side effect is flipping the related message's status to `escalated`, which is non-destructive and isolated so it never fails creation (FR-010, FR-011, FR-012, SR-06, T015, T060). Third hard guarantee
- **Snapshot semantics** — `intent_label`/`risk_level`/`risk_reason`/`ai_summary`/source ids are captured at creation and are **not** mutated by later upstream re-classification; `suggested_reply_id` is a live link to the reply (independent lifecycle) (SR-08, research.md Decision 2, T054)
- **Role split** — `staff` create + view; only `manager` may update (status/priority/assignee/notes), resolve, and cancel; `PATCH` and `/resolve` enforce `require_role("manager")` → 403 `INSUFFICIENT_ROLE` for staff (SR-04, FR-015, T013, T047)
- In-tenant reference validation is mandatory: `message_id`, `suggested_reply_id`, and `assigned_manager_id` must resolve within the JWT tenant before any write — and the assignee must have role `manager` (SR-03, T012, T045, T046)
- 404 (escalation/message not in tenant) vs 403 (exists in another tenant) mirrors Specs 005–011 SR-05 via the `_resolve_message_or_raise`/`get_escalation` helpers
- `EscalationStatus`/`EscalationPriority` persist as constrained VARCHARs (app-boundary validation), not native PG enums, for evolvability (consistent with Specs 008–011)
- State machine: `open → in_review → resolved | cancelled` (and `open → resolved|cancelled`); `resolved`/`cancelled` are terminal and field-immutable; invalid transitions → 422 `INVALID_STATE_TRANSITION` (T014, T058). `resolved_at` is set iff status is `resolved`
- Cancellation goes through `PATCH {"status":"cancelled"}` (no dedicated `/cancel` endpoint in the contract) (T018, T024)
- Priority defaults from the risk level when omitted (high risk → high/urgent, else medium), staff-overridable; the queue orders urgent/open first (research.md Decision 9, T014, T017)
- The optional AI summary (Phase 6) is **non-fatal** — `SummaryUnavailable` or `ESCALATION_SUMMARY_ENABLED=false` still creates the escalation without `ai_summary` (research.md Decision 10, T030)
- Duplicate escalations per message are allowed but discouraged; `GET /messages/{id}/escalations` surfaces existing ones and the UI warns/links (research.md Decision 12, T059)
- **Audit logging is out of scope for 012** — it is a **future integration** (the later audit-log feature, 013). This feature records actor (`created_by`, `assigned_manager_id`), action (status + notes), and timestamps for that feature to consume later; it builds no audit persistence, API, or UI here
- Notifications/paging/email, SLA timers/timeout auto-escalation, cross-tenant/shared escalations, full CRM, real WhatsApp API, and calendar syncing are all **out of scope** (spec Out of Scope)
