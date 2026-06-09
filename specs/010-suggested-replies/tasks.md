---
description: "Task list for Suggested Replies feature implementation"
---

# Tasks: Suggested Replies

**Branch**: `010-suggested-replies` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/010-suggested-replies/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `tenants` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping, `get_current_tenant_context`
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin` roles; `require_role`; Platform Admin block; `users` table; consistent `error_code` payload shape
- Spec 003 — Message Simulator: `messages` table + `body`; the message being replied to
- Spec 005 — Message Detail Page: conversation/message detail page with the "Suggested Reply" placeholder this feature replaces
- Spec 006 — Intent Classifier: `classification_results` (intent label) consumed as a precondition input
- Spec 007 — Risk Detection: `risk_assessments` (risk level/flag) consumed as a precondition input
- Spec 009 — RAG Over Tenant Documents: `rag_service.query(...)` + `rag_queries`/`rag_retrieval_results`; tenant-scoped sources + `grounded`/`no_source`/`no_documents` status; `RetrievalStatus` enum

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `suggested_replies` + one Alembic migration. `SuggestedReplyStatus` persisted as a constrained string (VARCHAR + app-boundary validation), not a native PG enum (consistent with Specs 008/009). Source id lists stored as JSONB.

**Config defaults** (research.md Resolved Configuration): `REPLY_MODEL_NAME="gpt-style-v1"`, `REPLY_PROMPT_VERSION="reply-prompt-v1"`, `REPLY_MAX_CHARS=1200`, `REPLY_SOURCE_SNIPPET_LIMIT=4`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US4]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–009 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant`/`tenants` (Spec 001), `User` + role enum (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `Message`/`messages` + `body` (Spec 003), `ClassificationResult` reader (Spec 006), `RiskAssessment` reader (Spec 007), `rag_service.query` + `RetrievalStatus` + `RagSource`/`rag_queries` (Spec 009), `NotFoundError`/`ForbiddenError` + their error→HTTP mapping (Spec 001), and the shared `error_code` envelope. Do NOT redefine any of these.
- [ ] T002 Add `REPLY_MODEL_NAME` (`"gpt-style-v1"`), `REPLY_PROMPT_VERSION` (`"reply-prompt-v1"`), `REPLY_MAX_CHARS` (1200), and `REPLY_SOURCE_SNIPPET_LIMIT` (4) to `backend/app/core/config.py` with documented defaults (research.md)
- [ ] T003 Verify `backend/tests/unit/`, `backend/tests/integration/`, and `backend/tests/eval/` exist with `__init__.py`; create any that are missing
- [ ] T004 Confirm how intent (Spec 006) and risk (Spec 007) results are read for a message (service/repo function or model query) and record the exact accessor signatures the precondition gate will call — so generation can detect "missing upstream" without re-running classification/risk

**Checkpoint**: Dependencies confirmed reused; config in place; upstream accessors identified.

---

## Phase 2: Database & Model (Foundational — Blocking)

**Purpose**: The `suggested_replies` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–8 cannot run without this phase.

- [ ] T005 [P] Create the `SuggestedReplyStatus` string enum (`draft_generated`, `edited`, `approved`, `rejected`) in `backend/app/schemas/suggested_reply.py` (shared by service + API layers) — per data-model.md
- [ ] T006 Create the `SuggestedReply` SQLAlchemy model in `backend/app/models/suggested_reply.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed (denormalised from message); `message_id` UUID FK→`messages.id` `ON DELETE CASCADE` NOT NULL indexed; `generated_text` TEXT NOT NULL (immutable original); `edited_text` TEXT NULL; `status` VARCHAR(20) NOT NULL default `draft_generated`; `source_document_ids` JSONB NOT NULL default `list`; `source_chunk_ids` JSONB NOT NULL default `list`; `grounded` Boolean NOT NULL default false; `model_name` VARCHAR(80) NOT NULL; `prompt_version` VARCHAR(40) NOT NULL; `rag_query_id` UUID FK→`rag_queries.id` NULL; `approved_by` UUID FK→`users.id` NULL; `approved_at` TIMESTAMPTZ NULL; `created_at`/`updated_at` TIMESTAMPTZ (server_default now, updated_at onupdate now); `message` relationship; `effective_text` property (`edited_text` if not None else `generated_text`); `Index("ix_reply_tenant_message", "tenant_id", "message_id")`, `Index("ix_reply_message_created", "message_id", "created_at")`, `Index("ix_reply_tenant_status", "tenant_id", "status")` — per data-model.md (depends on T005)
- [ ] T007 Create Alembic migration `backend/alembic/versions/00xx_create_suggested_replies.py`: create `suggested_replies` with all columns, the three FKs (`tenant_id`→`tenants.id`, `message_id`→`messages.id` ON DELETE CASCADE, `rag_query_id`→`rag_queries.id`, `approved_by`→`users.id`), defaults (`status='draft_generated'`, `grounded=false`, JSONB `[]` for source id lists), and the three composite indexes; provide a correct `downgrade()` dropping the table + indexes (depends on T006)

**Checkpoint**: `alembic upgrade head` creates the table; ORM model importable; `effective_text` property works.

---

## Phase 3: Schemas (Foundational — Blocking)

**Purpose**: Pydantic request/response models shared by the service and endpoints.

- [ ] T008 Add Pydantic models to `backend/app/schemas/suggested_reply.py` (alongside `SuggestedReplyStatus` from T005) per data-model.md: `ReplySource` (`document_id`, `document_title`, `document_type`, `chunk_id`, `snippet`), `GenerateRequest` (`force: bool = False`), `EditRequest` (`edited_text: str = Field(min_length=1, max_length=4000)` + `field_validator` stripping/rejecting blank), `RejectRequest` (optional `reason: str | None = None`), `SuggestedReplyResponse` (`id`, `message_id`, `generated_text`, `edited_text`, `effective_text`, `status: SuggestedReplyStatus`, `grounded`, `sources: list[ReplySource]`, `model_name`, `prompt_version`, `approved_by`, `approved_at`, `created_at`, `updated_at`; `from_attributes=True`), `SuggestedReplyListResponse` (`items: list[SuggestedReplyResponse]`, `total: int`)

**Checkpoint**: Schemas importable — AI + service phases can begin.

---

## Phase 4: AI Prompt Builder & Generator (Foundational — Blocking, unit-tested)

**Purpose**: The versioned prompt builder (grounded/refusal/tone) and the generator interface are the AI core. Build and unit-test them in isolation before the service (plan.md Build Order). The generator is **behind an interface** — an LLM in prod, a deterministic stub in tests. **BLOCKS US1, US2, US4.**

### Prompt builder

- [ ] T009 [P] [US1] Implement the versioned prompt builder in `backend/app/ai/reply_prompt.py`: a `PROMPT_VERSION` constant (= `REPLY_PROMPT_VERSION`); `grounded(message, classification, risk, sources) -> str` assembling message text + intent label + risk level/flag + the bounded RAG source snippets (titles/types/snippets, capped at `REPLY_SOURCE_SNIPPET_LIMIT`), instructing: polite/professional/concise wedding-event tone, answer policy/package facts **only** from the provided snippets and reference them, never claim a payment is confirmed unless verified, never promise availability unless supported (GR-01, FR-014, AI Behavior)
- [ ] T010 [P] [US2] Implement `refusal(message, risk) -> str` in `backend/app/ai/reply_prompt.py`: a polite draft stating the information is not covered in the uploaded documents and that the team will confirm / recommends human review — no invented policy/price/availability (GR-02, FR-004)
- [ ] T011 [US4] Add risk-based tone parameterisation to both templates in `backend/app/ai/reply_prompt.py`: high-risk → careful, empathetic, de-escalating, may include a "consider manager escalation" note (text only); low-risk → friendly/efficient. No escalation/task is ever created (FR-010, Decision 7, AC-05) (depends on T009, T010)
- [ ] T012 [P] [US1] Write `backend/tests/unit/test_reply_prompt.py`: grounded-vs-refusal template selection given RAG status; snippet bounding to `REPLY_SOURCE_SNIPPET_LIMIT`; tone markers differ by risk level; `PROMPT_VERSION` is stamped; grounded template includes source titles, refusal template asserts no policy facts (plan.md Testing) (depends on T011)

### Generator interface

- [ ] T013 [US1] Implement the `ReplyGenerator` interface in `backend/app/ai/reply_generator.py`: `generate(prompt: str) -> str` exposing `model_name` (= `REPLY_MODEL_NAME`) and bounded to `REPLY_MAX_CHARS`; an LLM-backed impl for prod plus a **deterministic stub** for tests; raise typed `GenerationUnavailable` on model failure (research.md Decision 1, Decision 9)
- [ ] T014 [P] [US1] Write `backend/tests/unit/test_reply_generator.py` (or fold into the service unit tests): the stub is deterministic, output respects `REPLY_MAX_CHARS`, and `GenerationUnavailable` propagates when the model is forced unavailable (depends on T013)

**Checkpoint**: Prompt builder + generator are correct and testable without a live LLM; refusal vs grounded selection is unit-proven.

---

## Phase 5: Suggested Reply Service (Foundational — Blocking)

**Purpose**: Orchestrate generate / list / get / edit / approve / reject with tenant resolution, the precondition gate, the grounding/refusal branch (a code path, not a prompt request), citation validation, and the status state machine. **BLOCKS the API in Phase 6.**

- [ ] T015 Define typed errors in `backend/app/services/suggested_reply_service.py` (or the shared errors module): `PreconditionNotMet` (→409 `PRECONDITION_NOT_MET`), `PreconditionError` (empty body →422), `InvalidStateTransition` (→422 `INVALID_STATE_TRANSITION`), `EmptyReplyText` (→422 `EMPTY_REPLY_TEXT`), `ModelUnavailableError` (→503 `MODEL_UNAVAILABLE`); reuse `NotFoundError`/`ForbiddenError` (Spec 001) for 404/403 (data-model.md error→HTTP mapping)
- [ ] T016 Implement `_resolve_message_or_raise(session, tenant_id, message_id)` and `get(session, tenant_id, reply_id)` (resolve reply) in `backend/app/services/suggested_reply_service.py`: `NotFoundError` (404) if absent, `ForbiddenError` (403) if in another tenant — mirroring Specs 005–009 SR-05 (depends on T006)
- [ ] T017 Implement `_assert_not_terminal(reply)` in `backend/app/services/suggested_reply_service.py`: raise `InvalidStateTransition` when `status ∈ {approved, rejected}` (state machine; FR-009) (depends on T015)
- [ ] T018 Implement `_is_policy_or_package(intent_label) -> bool` in `backend/app/services/suggested_reply_service.py`: true for intents needing policy/package facts (e.g. pricing/package, cancellation/refund/deposit) so the refusal branch only triggers for grounded-fact questions, not greetings (US2 scenario 3) (depends on T004)
- [ ] T019 Implement `_validate_sources(rag_sources) -> list[ReplySource]` in `backend/app/services/suggested_reply_service.py`: map the Spec 009 retrieval result to `ReplySource`s; **never** include a source id not present in the retrieval result (GR-05) (depends on T008)
- [ ] T020 [US1][US2][US4] Implement `generate(session, tenant_id, user, message_id, force=False) -> SuggestedReply` in `backend/app/services/suggested_reply_service.py`: resolve message (404/403); empty body → `PreconditionError` (422); read intent (006) + risk (007), if either missing → `PreconditionNotMet` (409); call `rag_service.query(session, tenant_id, message.body, message_id=message_id)` (tenant-scoped, Spec 009); **branch**: if `_is_policy_or_package` and RAG status ∈ {`no_source`,`no_documents`} → `reply_prompt.refusal(...)`, empty sources, `grounded=False`; else `generator.generate(reply_prompt.grounded(...))` (catch `GenerationUnavailable` → `ModelUnavailableError` 503, no draft stored), `sources=_validate_sources(rag.sources)`, `grounded=bool(sources)`; persist a new `SuggestedReply` row with `status=draft_generated`, `generated_text`, source id lists, `grounded`, `model_name`, `prompt_version`, `rag_query_id`; never overwrite an existing approved row (FR-001..FR-004, FR-013, FR-015, GR-01/02/03/05, AC-01..AC-04, AC-11, AC-16, AC-18) (depends on T011, T013, T016, T018, T019)
- [ ] T021 [US3] Implement `list_for_message(session, tenant_id, message_id) -> SuggestedReplyListResponse` in `backend/app/services/suggested_reply_service.py`: resolve message (404/403); return replies for the message ordered newest-first with `total` (AC-12) (depends on T016)
- [ ] T022 [US3] Implement `edit(session, tenant_id, reply_id, edited_text) -> SuggestedReply` in `backend/app/services/suggested_reply_service.py`: `get` (404/403); `_assert_not_terminal`; blank text → `EmptyReplyText` (422); store `edited_text` (preserve `generated_text`), set status `edited`, commit (FR-006, AC-06, AC-09) (depends on T016, T017)
- [ ] T023 [US3] Implement `approve(session, tenant_id, user, reply_id) -> SuggestedReply` in `backend/app/services/suggested_reply_service.py`: `get` (404/403); `_assert_not_terminal`; set status `approved`, `approved_by=user.id`, `approved_at=now`, commit — **performs no send and creates no task/escalation** (FR-005, FR-007, SR-06, SR-07, AC-07, AC-15) (depends on T016, T017)
- [ ] T024 [US3] Implement `reject(session, tenant_id, reply_id, reason=None) -> SuggestedReply` in `backend/app/services/suggested_reply_service.py`: `get` (404/403); `_assert_not_terminal`; set status `rejected`, commit; the optional `reason` triggers no action (FR-008, AC-08, AC-09) (depends on T016, T017)
- [ ] T025 Implement `_to_response(session, tenant_id, reply) -> SuggestedReplyResponse` in `backend/app/services/suggested_reply_service.py`: assemble `sources` from the stored source ids by reading the message-tenant RAG results (tenant-scoped; never cross-tenant), populate `effective_text`; used by all endpoints (FR-003, GR-03, GR-06) (depends on T008, T016)

**Checkpoint**: Service complete; precondition gate, grounding/refusal code path, citation validation, and state machine all enforced; no send/task/escalation anywhere.

---

## Phase 6: API Endpoints (User Stories 1–4)

**Purpose**: Expose the six endpoints with `require_role("staff", "manager")` and error→HTTP mapping. `tenant_id` and `approved_by` are always derived from the JWT; any client-supplied tenant is ignored. **🎯 MVP backend deliverable. No send/task/escalation endpoint exists.**

- [ ] T026 [US1] Implement `POST /api/messages/{message_id}/suggested-replies` in `backend/app/api/v1/suggested_replies.py`: `require_role("staff", "manager")`; parse optional `GenerateRequest`; call `service.generate`; return `SuggestedReplyResponse` **201**. Map `PreconditionNotMet`→409, `PreconditionError`→422, `ModelUnavailableError`→503 `MODEL_UNAVAILABLE`, `NotFoundError`→404 `MESSAGE_NOT_FOUND`, `ForbiddenError`→403 `CROSS_TENANT_FORBIDDEN` (contracts §1, AC-01, AC-02, AC-03, AC-18) (depends on T020)
- [ ] T027 [US3] Implement `GET /api/messages/{message_id}/suggested-replies` in `backend/app/api/v1/suggested_replies.py`: `require_role("staff", "manager")`; call `service.list_for_message`; return `SuggestedReplyListResponse` (200); cross-tenant → 404/403 (contracts §2, AC-12) (depends on T021)
- [ ] T028 [US3] Implement `GET /api/suggested-replies/{reply_id}` in `backend/app/api/v1/suggested_replies.py`: `require_role("staff", "manager")`; call `service.get` + `_to_response`; return `SuggestedReplyResponse` (200); cross-tenant → 403 `CROSS_TENANT_FORBIDDEN`, missing → 404 `REPLY_NOT_FOUND` (contracts §3, AC-13) (depends on T025)
- [ ] T029 [US3] Implement `PATCH /api/suggested-replies/{reply_id}` in `backend/app/api/v1/suggested_replies.py`: `require_role("staff", "manager")`; validate `EditRequest`; call `service.edit`; return updated `SuggestedReplyResponse` (200); empty text → 422 `EMPTY_REPLY_TEXT`, terminal → 422 `INVALID_STATE_TRANSITION` (contracts §4, AC-06, AC-09) (depends on T022)
- [ ] T030 [US3] Implement `POST /api/suggested-replies/{reply_id}/approve` in `backend/app/api/v1/suggested_replies.py`: `require_role("staff", "manager")`; call `service.approve` with the JWT user; return `SuggestedReplyResponse` (200) with `approved_by`/`approved_at`; terminal → 422 `INVALID_STATE_TRANSITION` — **no send** (contracts §5, AC-07, AC-15) (depends on T023)
- [ ] T031 [US3] Implement `POST /api/suggested-replies/{reply_id}/reject` in `backend/app/api/v1/suggested_replies.py`: `require_role("staff", "manager")`; parse optional `RejectRequest`; call `service.reject`; return `SuggestedReplyResponse` (200); terminal → 422 `INVALID_STATE_TRANSITION` (contracts §6, AC-08, AC-09) (depends on T024)
- [ ] T032 Mount the suggested-replies router at `/api` in `backend/app/main.py` so all six routes resolve (plan.md Backend Tasks #8) (depends on T026–T031)
- [ ] T033 [US3] Surface the latest suggested reply to the detail page: extend `backend/app/services/conversation_service.py` (or expose the dedicated list/get fetch) so the Spec 005 detail response can carry/trigger the message's latest reply + sources + status (plan.md Modified files, FR-011) (depends on T021)

**Checkpoint**: All six endpoints return per the contract; role matrix + tenant resolution + state machine enforced. Backend MVP complete.

---

## Phase 7: Frontend Integration (User Story 3 + display of 1/2/4)

**Purpose**: Replace the Spec 005 "Suggested Reply" placeholder with the real panel — text, sources, status, review controls, refusal/no-source warning, and a clear "not auto-sent" notice.

- [ ] T034 [P] [US3] Add TS types to `frontend/src/types/suggestedReply.ts`: `SuggestedReplyStatus`, `ReplySource`, `SuggestedReply` (data-model.md Frontend Types)
- [ ] T035 [P] [US3] Add the typed API client `frontend/src/api/suggestedReplies.ts`: `generate(messageId, force?)`, `list(messageId)`, `get(replyId)`, `edit(replyId, text)`, `approve(replyId)`, `reject(replyId, reason?)` — calling the six endpoints with the auth header (depends on T034)
- [ ] T036 [US1][US2] Implement `frontend/src/components/replies/ReplySources.tsx`: lists each `ReplySource` (document title, type badge, snippet) reusing the Spec 009 source display; renders nothing/an empty state when sources are empty (plan.md Frontend #5, AC-17) (depends on T034)
- [ ] T037 [US3] Implement `frontend/src/components/replies/ReplyEditor.tsx`: editable textarea prefilled with `effective_text`; Save (edit), Approve, Reject buttons; disabled in terminal (`approved`/`rejected`) states; empty-text guard; buttons call the correct API client methods (plan.md Frontend #4, AC-17) (depends on T035)
- [ ] T038 [US3] Implement `frontend/src/components/replies/SuggestedReplyPanel.tsx`: shows effective text + status badge + grounded/refusal indicator + `ReplySources` + `ReplyEditor`; a **no-source/refusal warning** when `grounded=false`; a **prominent "This reply is not sent automatically — review and approve" notice**; states: no-reply-yet (Generate CTA), generating (loading), draft/edited/approved (shows reviewer + time)/rejected, precondition-missing (prompt to run upstream), model-unavailable (error) (FR-011, AC-03, AC-17; spec Outputs) (depends on T036, T037)
- [ ] T039 [US3] Wire `SuggestedReplyPanel` into the Spec 005 conversation/message detail page (`frontend/src/pages/ConversationDetailPage`), **replacing** the "Suggested Reply" placeholder; leave the Create Task / Escalate placeholders untouched (plan.md Frontend #3, spec Assumptions) (depends on T038)

**Checkpoint**: Detail page shows the draft (or refusal), sources, status, and review controls; the "not auto-sent" notice is visible; staff can edit/approve/reject from the UI.

---

## Phase 8: Frontend Tests

**Purpose**: Render/interaction tests for the panel, editor, sources, and the no-send notice.

- [ ] T040 [P] [US3] `SuggestedReplyPanel` render tests in `frontend/src/components/replies/__tests__/SuggestedReplyPanel.test.tsx`: grounded draft renders text + `ReplySources`; refusal (`grounded=false`) renders the no-source warning and empty sources; loading + error (model-unavailable) + no-reply-yet states render; the "not sent automatically" notice appears (AC-17)
- [ ] T041 [P] [US3] `ReplyEditor` interaction test: staff can edit the generated text; Save/Approve/Reject call the correct endpoints; editor is disabled in terminal states (AC-06, AC-17) (depends on T037)
- [ ] T042 [P] [US3] `ReplySources` render test: asserts each source's document title, type badge, and snippet are displayed (AC-17) (depends on T036)

**Checkpoint**: Frontend states + interactions verified.

---

## Phase 9: Tenant Isolation & Role Security Tests (cross-cutting)

**Purpose**: Prove Tenant A never accesses Tenant B replies/sources, `tenant_id` comes only from the JWT, and the role matrix holds. `backend/tests/integration/test_suggested_replies.py`.

- [ ] T043 [P] Generate a draft for the caller's **own** tenant message → 201, reply `tenant_id` = caller's tenant, all `source_document_ids`/`source_chunk_ids` belong to that tenant (AC-01, AC-11, SR-02, SR-03)
- [ ] T044 [P] A grounded draft references **only** the message tenant's RAG sources — no cross-tenant source id appears (AC-11, GR-03, defence-in-depth assertion)
- [ ] T045 [P] Tenant A cannot read Tenant B reply: `GET /suggested-replies/{B_reply}` as A → 403/404, no text/sources leaked (AC-10, AC-13)
- [ ] T046 [P] Tenant A cannot edit/approve/reject Tenant B reply: each → 403/404, no change occurs (AC-10, FR-012)
- [ ] T047 [P] Tenant A cannot generate for a Tenant B message: `POST /messages/{B_msg}/suggested-replies` as A → 403/404; no draft stored (SR-05)
- [ ] T048 [P] Client-supplied `tenant_id` is ignored: a `tenant_id` injected into the body/query does not change ownership — the reply still scopes to the JWT tenant; `approved_by` is always the JWT user, not a client value (SR-01, SR-08)
- [ ] T049 [P] Platform Admin → 403 `INSUFFICIENT_ROLE` on **all six** endpoints (generate, list, get, edit, approve, reject) (AC-14, SR-04); unauthenticated → 401 on each
- [ ] T050 [P] Both `staff` and `manager` can generate/list/get/edit/approve/reject their own tenant replies (role matrix; SR-04)

**Checkpoint**: Tenant isolation and the role matrix are proven; no cross-tenant bypass; no client-spoofable provenance.

---

## Phase 10: Suggested Reply Behaviour & Integration Tests

**Purpose**: Verify generation, grounding/refusal, tone, the state machine, no-send/no-side-effects, multiple drafts, preconditions, and the demo scenarios. `backend/tests/integration/test_suggested_replies.py` + `backend/tests/eval/test_reply_grounding.py`.

- [ ] T051 [P] Generation creates a `SuggestedReply` linked to the message with status `draft_generated`, non-empty `generated_text`, `model_name`, `prompt_version`, timestamps (AC-01)
- [ ] T052 [P] Grounded pricing/package request: a `pricing_request` message with the package document processed → draft records non-empty `source_document_ids`/`source_chunk_ids`, `grounded=true`, and references the package source (AC-02; quickstart Scenario 1)
- [ ] T053 [P] Grounded cancellation/deposit request: a cancellation message → draft grounded in the cancellation/deposit policy source, careful (high-risk) tone (quickstart Scenario 2)
- [ ] T054 [P] Refusal on no source: an unsupported policy/package question (fireworks/drones/celebrity singer) with RAG `no_source`/`no_documents` → draft asserts no policy/price/availability, states info not in uploaded documents + recommends human review, empty source lists, `grounded=false` (AC-03, FR-004, GR-02; quickstart Scenario 3)
- [ ] T055 [P] No uncited facts: assert a grounded draft asserts no policy/pricing/availability fact absent from its cited sources; a non-policy greeting with no sources → polite generic reply, no unsupported assertions (AC-04, US2 scenario 3)
- [ ] T056 [P] High-risk tone + no side effects: a high-risk complaint → empathetic/de-escalating wording, may recommend escalation in text, and **no task and no escalation entity created** by the call (AC-05, FR-010, SR-07; quickstart Scenario 4)
- [ ] T057 [P] Edit stores `edited_text`, preserves `generated_text`, sets status `edited`, `effective_text` = the edit (AC-06)
- [ ] T058 [P] Approve sets status `approved`, records `approved_by`+`approved_at`, and **performs no send** (assert no send/transport side effect) (AC-07, AC-15)
- [ ] T059 [P] Reject sets status `rejected`; optional reason triggers no action (AC-08)
- [ ] T060 [P] Invalid state transitions → 422 `INVALID_STATE_TRANSITION`: edit an `approved`/`rejected` reply; approve a `rejected` reply; reject an `approved` reply; edit-to-empty → 422 `EMPTY_REPLY_TEXT` (AC-09, FR-009)
- [ ] T061 [P] No send path exists: assert there is no endpoint, service method, status, or field representing "sent"; approval never transmits anything (AC-15, SR-06)
- [ ] T062 [P] Multiple drafts: generating twice creates two separate rows (history); approving one does not overwrite or alter the other; an `approved` reply is never overwritten by regeneration (`force=true`) (AC-16, FR-015)
- [ ] T063 [P] Precondition gate: generating for a message missing intent and/or risk → 409 `PRECONDITION_NOT_MET`, no draft stored; empty message body → 422 (AC-18, FR-001) (depends on T004)
- [ ] T064 [P] Model unavailable: force `GenerationUnavailable` → 503 `MODEL_UNAVAILABLE`, no malformed draft stored, retry allowed (spec Failure Cases)
- [ ] T065 Eval harness `backend/tests/eval/test_reply_grounding.py`: over the two-tenant demo corpus, grounded replies cite the correct **tenant** source (EW pricing → Premium Wedding Package; RE pricing → Luxury Wedding Package), refusal fires for unsupported questions, high-risk tone present, and **no cross-tenant source ever appears** in any draft (plan.md Eval; quickstart Scenarios 1–5)

**Checkpoint**: All 18 acceptance criteria covered by tests; grounding/refusal, tone, state machine, no-send, and demo isolation verified.

---

## Phase 11: Quickstart & Manual Validation

**Purpose**: Execute the five-scenario quickstart end to end (quickstart.md). Requires Spec 009 documents uploaded **and processed** per tenant first.

- [ ] T066 Run migrations (`alembic upgrade head`); log in as staff of both demo tenants; confirm EW + RE documents are uploaded and processed (Spec 009) so RAG has chunks
- [ ] T067 Scenario 1 — pricing request with matching package document (EW) → `draft_generated`, `grounded=true`, sources include the EW package document
- [ ] T068 Scenario 2 — cancellation request with matching cancellation/deposit policy (EW) → grounded in deposit/cancellation policy, careful (high-risk) tone, may note escalation; no escalation created
- [ ] T069 Scenario 3 — unsupported fireworks/drones/celebrity singer request → `grounded=false`, empty sources, refusal text (no invented policy/price)
- [ ] T070 Scenario 4 — high-risk complaint ("very unhappy ... wedding next week") → empathetic, de-escalating wording; confirm **no task or escalation entity** is created
- [ ] T071 Scenario 5 — tenant isolation: same pricing question for EW and RE → EW cites the EW package only, RE cites the RE package only; reading an EW reply id as RE → 403 `CROSS_TENANT_FORBIDDEN`
- [ ] T072 Human review path: edit a draft → status `edited`, `effective_text` = edit, `generated_text` preserved; approve → status `approved` + reviewer/time, nothing sent; editing the approved reply → 422 `INVALID_STATE_TRANSITION`; reject another draft → status `rejected`
- [ ] T073 Role/precondition checks: Platform Admin generate → `INSUFFICIENT_ROLE`; a message missing intent/risk → 409 `PRECONDITION_NOT_MET`; confirm in the UI the panel shows the draft, sources, status, and the "not sent automatically" notice

**Checkpoint**: Quickstart passes end to end; grounding, refusal, tone, review lifecycle, and tenant isolation demonstrated live.

---

## Phase 12: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T074 Verify AC-01..AC-18 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T075 Walk `checklists/requirements.md` Functional / AI / RAG Grounding / Human Review / Security / Tenant Isolation / API / Data / Testing sections and tick each implemented item
- [ ] T076 Confirm Out-of-Scope items remain **unbuilt**: no reply sending (any transport), no task creation, no escalation workflow (recommendation text only), no re-implementation of intent/risk/RAG, no audit-log persistence/API/UI, no multi-turn/threaded generation, no auto-approval/auto-regeneration, no tone/style config UI, no full guardrail service, no short-term memory, no WhatsApp/calendar/CRM (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 010 verified against spec + checklist; human-reviewed grounded replies delivered with the two hard guarantees (no invented answers, no auto-send) proven.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (DB/model)** → depends on Phase 1; **BLOCKS everything**.
- **Phase 3 (Schemas)** → depends on T005; blocks service + API.
- **Phase 4 (Prompt + Generator)** → depends on Phases 2–3; unit-tested in isolation; **blocks the service**. Prompt (T009–T012) and Generator (T013–T014) are independent and run in parallel.
- **Phase 5 (Service)** → depends on Phase 4 (and the upstream accessors from T004 + Spec 009 `rag_service.query`); blocks the API.
- **Phase 6 (API)** → depends on Phase 5; **MVP backend deliverable**.
- **Phase 7 (Frontend)** → depends on Phase 6 (consumes the endpoints).
- **Phase 8 (Frontend tests)** → depends on Phase 7.
- **Phase 9 (Isolation/role tests)** + **Phase 10 (Behaviour/eval tests)** → depend on Phase 6 (demo corpus + upstream signals available).
- **Phase 11 (Quickstart)** → depends on Phases 6–7 and processed Spec 009 documents.
- **Phase 12 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3 — generation, refusal, human review)

1. Phase 1: Setup (config + upstream accessors)
2. Phase 2: DB + model + migration (**CRITICAL**)
3. Phase 3: Schemas
4. Phase 4: Prompt builder (grounded/refusal/tone) + generator interface + stub (unit-tested)
5. Phase 5: Service (precondition gate → grounding/refusal code path → citation validation → state machine)
6. Phase 6: API (six endpoints + router mount + error/state mapping)
7. **STOP and VALIDATE**: run unit + isolation tests; confirm grounded vs refusal, no invented facts, no-send path, state machine, tenant scoping, client-tenant override ignored
8. Phase 9 + 10: full isolation + behaviour + eval coverage (AC-01..AC-18)

### Incremental Delivery

1. Setup + DB + prompt/generator + schemas → foundation ready
2. US1 (generate grounded draft) → the core output exists (**generation MVP**)
3. US2 (refuse without evidence) → the safety guarantee is enforced as a code path
4. US3 (edit/approve/reject) → human-in-the-loop lifecycle, no auto-send (**review MVP**)
5. US4 (high-risk tone) → empathetic wording for risky messages
6. Frontend → SuggestedReplyPanel + editor + sources + "not auto-sent" notice
7. Tests + quickstart + eval + acceptance → all 18 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id` and `approved_by` are **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SR-01, SR-08); any `tenant_id` in the body/query is ignored (T048)
- **The refusal path is a code path, not a prompt request** — the service decides grounded vs refusal from the Spec 009 RAG status *before* generation, so an LLM can never invent a policy answer (FR-004, GR-02, research.md Decision 2). This is the first of the two hard guarantees
- **There is no send path** — no endpoint, service method, status, queue, or field represents "sent"; `approved` is human-acceptance only (FR-005, SR-06, AC-15). This is the second hard guarantee (T061)
- Cited sources are validated ⊆ the actual retrieval result (GR-05, T019); cross-tenant sources can never enter the prompt or the stored ids (SR-03, GR-03, T044)
- 404 (message/reply not in tenant) vs 403 (exists in another tenant) mirrors Specs 005–009 SR-05 via the `_resolve_*_or_raise`/`get` helpers
- `SuggestedReplyStatus` persists as a constrained VARCHAR (app-boundary validation), not a native PG enum, for evolvability (consistent with Specs 008/009)
- `generated_text` is **immutable** after creation; edits live in `edited_text`; **effective text** = `edited_text` if present else `generated_text` (data-model.md invariants)
- State machine: `draft_generated → edited → approved | rejected`; `approved`/`rejected` are terminal and content-immutable; invalid transitions → 422 `INVALID_STATE_TRANSITION` (T017, T060)
- Regeneration creates a **new** row (history); an `approved` reply is never overwritten (FR-015, AC-16, T062)
- Generation requires upstream intent (006) + risk (007) + a RAG retrieval (009); missing → 409 `PRECONDITION_NOT_MET` — the feature consumes these, it does not re-implement classification/risk/retrieval
- The feature creates **no tasks and no escalations** (drafts may *recommend* escalation in text only) (FR-010, SR-07) — those are later features
- **Audit logging is out of scope for 010** — deferred to the later audit-log feature (013). If a post-action event hook is added, it is a no-op/future-integration stub only; build no audit persistence, API, or UI here
- **Full guardrails are out of scope for 010** — deferred to feature 014. This feature includes only the basic no-source/no-invention behaviour specified here (GR-02), not a general guardrail service
- Short-term memory, multi-turn/threaded generation, real WhatsApp API, calendar syncing, and full CRM are all **out of scope** (spec Out of Scope)
