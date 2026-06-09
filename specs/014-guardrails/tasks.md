---
description: "Task list for Guardrails feature implementation"
---

# Tasks: Guardrails

**Branch**: `014-guardrails` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/014-guardrails/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `tenants` table, `tenant_id` isolation, server-side tenant-scoped retrieval, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping, `get_current_tenant_context`, the tenant registry (names/slugs/ids) used for cross-tenant detection
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin` roles; `require_role`; Platform Admin block; `tenant_id`/`user_id`/`role` from JWT only
- Spec 003 — Message Simulator: `messages` table; the client message text is the scanned input; the original body is stored as-is (never redacted)
- Spec 005 — Message Detail Page: surfaces the professional refusal/hold banner + a message's guardrail decisions panel
- Spec 009 — RAG Over Tenant Documents: provides the retrieved sources (chunk texts + `source_document_ids`) that grounding is validated against; tenant-scoped retrieval; the `rag_no_source_found` signal
- Spec 010 — Suggested Replies: `suggested_replies` table; the AI draft checked by `check_ai_output`; the human-review/approve step is preserved (never auto-sent)
- Spec 013 — Audit Logs: `AuditService.log_event` / `log_cross_tenant_blocked` (best-effort, never raises) for `guardrail_refusal` / `cross_tenant_access_blocked` / `unsupported_answer_refused`; the audit-side redactor backstop

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `guardrail_decisions` + one Alembic migration. **Append-only** — no `updated_at`, no update/delete path (mirrors Spec 013 audit logs). `category`/`action`/`severity` persisted as constrained strings (VARCHAR + app-boundary enum validation), `metadata` as JSONB. Loose FKs to `messages`/`suggested_replies` (`ON DELETE SET NULL`) so deleting a business row never erases the safety trail. No column changes to existing tables.

**Config defaults** (plan.md #8): `GUARDRAILS_ENABLED=true`, `GUARDRAIL_LOG_ALLOW_DECISIONS=false`, `GUARDRAIL_MAX_SCAN_CHARS=20000`, `GUARDRAIL_DECISIONS_MAX_LIMIT=200`, `GUARDRAIL_STAFF_MESSAGE_VIEW_ENABLED=true`, `GUARDRAIL_GROUNDING_THRESHOLD` (overlap ratio for grounding).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US4]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–013 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant`/`tenants` + tenant registry lookup of other-tenant names/slugs/ids (Spec 001), `require_role` + `get_current_tenant_context` (Spec 002), `Message`/`messages` (Spec 003), the RAG sources accessor (chunk texts + `source_document_ids`) + `rag_no_source_found` signal (Spec 009), `SuggestedReply`/`suggested_replies` (Spec 010), `AuditService.log_event` + `log_cross_tenant_blocked` + the audit redactor (Spec 013), `NotFoundError`/`ForbiddenError` + their error→HTTP mapping (Spec 001), and the shared `error_code` envelope. Do NOT redefine any of these.
- [ ] T002 Add the `GUARDRAIL_*` settings to `backend/app/core/config.py` with documented defaults: `GUARDRAILS_ENABLED=true`, `GUARDRAIL_LOG_ALLOW_DECISIONS=false`, `GUARDRAIL_MAX_SCAN_CHARS=20000`, `GUARDRAIL_DECISIONS_MAX_LIMIT=200`, `GUARDRAIL_STAFF_MESSAGE_VIEW_ENABLED=true`, `GUARDRAIL_GROUNDING_THRESHOLD` (plan.md #8)
- [ ] T003 Record the exact upstream accessor signatures the reply path (Spec 010) and grounding will call — the RAG sources reader (tenant-scoped chunk texts + `source_document_ids`, Spec 009), the `rag_no_source_found` signal, and the draft text from Spec 010 — all tenant-scoped, all read-only; confirm they degrade gracefully when RAG returns no source (FR-006, GR-02, AC-05)
- [ ] T004 Confirm the demo seed has ≥1 uploaded tenant document for Elegant Weddings (grounded vs. unsupported tests) and a staff + manager account per tenant for both Elegant Weddings and Royal Events (quickstart.md Prerequisites)
- [ ] T005 Verify `backend/tests/unit/` and `backend/tests/integration/` exist with `__init__.py`; create any that are missing

**Checkpoint**: Dependencies confirmed reused; config in place; RAG/draft accessors + no-source signal recorded; demo data ready.

---

## Phase 2: Database & Model (Foundational — Blocking)

**Purpose**: The append-only `guardrail_decisions` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–9 cannot run without this phase.

- [ ] T006 Create the `GuardrailDecision` SQLAlchemy model in `backend/app/models/guardrail_decision.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `message_id` UUID FK→`messages.id` `ON DELETE SET NULL` NULL indexed; `suggested_reply_id` UUID FK→`suggested_replies.id` `ON DELETE SET NULL` NULL; `category` VARCHAR(40) NOT NULL; `action` VARCHAR(24) NOT NULL; `severity` VARCHAR(12) NOT NULL default `"info"`; `reason` TEXT NULL; `redacted_text` TEXT NULL; `metadata_` mapped to column `"metadata"` JSONB NOT NULL default `dict`; `created_at` TIMESTAMPTZ server_default now; **no `updated_at`**; indexes `ix_guardrail_tenant_created` (`tenant_id`,`created_at`), `ix_guardrail_tenant_category` (`tenant_id`,`category`), `ix_guardrail_tenant_action` (`tenant_id`,`action`), `ix_guardrail_tenant_severity` (`tenant_id`,`severity`), `ix_guardrail_tenant_message` (`tenant_id`,`message_id`) — per data-model.md
- [ ] T007 Create Alembic migration `backend/alembic/versions/00xx_create_guardrail_decisions.py`: create `guardrail_decisions` with all columns, the FKs (`tenant_id`→`tenants.id`, `message_id`→`messages.id` `ON DELETE SET NULL`, `suggested_reply_id`→`suggested_replies.id` `ON DELETE SET NULL`), defaults (`severity='info'`, JSONB `{}` for `metadata`), and the five composite indexes; **no** `updated_at`; provide a correct `downgrade()` dropping the table + indexes (depends on T006)
- [ ] T008 Append-only enforcement (mirror Spec 013): in the migration, revoke `UPDATE, DELETE` on `guardrail_decisions` for the app DB role **or** add a `BEFORE UPDATE OR DELETE` trigger that raises; document the chosen approach in the migration (data-model.md "Append-only enforcement") (depends on T007)

**Checkpoint**: `alembic upgrade head` creates the append-only table; ORM model importable; UPDATE/DELETE blocked at the data layer.

---

## Phase 3: Schemas & Enums (Foundational — Blocking)

**Purpose**: Enums + Pydantic request/response/DTO models shared by the rules, service, and endpoints. List items are a summary; the full response carries `redacted_text` + `metadata`.

- [ ] T009 [P] Create the `GuardrailCategory` (`prompt_injection`, `system_prompt_disclosure`, `cross_tenant_access`, `unsupported_answer`, `pii_redaction`, `unsafe_or_unprofessional_reply`, `secret_or_token_exposure`, `human_review_required`), `GuardrailAction` (`allow`, `warn`, `redact`, `refuse`, `require_human_review`), and `GuardrailSeverity` (`info`, `low`, `medium`, `high`, `security`) string enums in `backend/app/schemas/guardrails.py` (shared by service + API) — per data-model.md
- [ ] T010 Add Pydantic models to `backend/app/schemas/guardrails.py` (alongside the enums) per data-model.md: `CheckInputRequest` (`text: str` 0–20000, `message_id: UUID | None`), `CheckOutputRequest` (`draft_text: str` ≤20000, `message_id`/`suggested_reply_id: UUID | None`, `source_document_ids: list[UUID]=[]`, `sources: list[str]=[]` (not persisted)), `CheckResult` (`category: GuardrailCategory | None`, `action`, `severity`, `reason: str | None`, `proceed: bool`, `display_text: str | None`, `decision_id: UUID | None`, `metadata: dict`), `GuardrailDecisionFilters` (`category`/`action`/`severity`/`message_id`/`created_from`/`created_to`, all optional), `GuardrailDecisionListItem` (`id`, `created_at`, `category`, `action`, `severity`, `message_id`, `suggested_reply_id`, `reason`; `from_attributes=True`), `GuardrailDecisionResponse(GuardrailDecisionListItem)` (adds `tenant_id`, `redacted_text`, `metadata`), `GuardrailDecisionListResponse` (`items`, `total`, `limit`, `offset`), `MessageGuardrailDecisionsResponse` (`message_id`, `items`, `total`) (depends on T009)

**Checkpoint**: Enums + schemas importable — detection/redaction/grounding and the service phase can begin.

---

## Phase 4: Detection, Redaction & Grounding (Foundational — Blocking, unit-tested)

**Purpose**: The rule/heuristic detection layer, the shared redactor, and the grounding validator — the pure, dependency-free building blocks. These are unit-tested in isolation (precision + the critical benign-topic negatives) **before** the service wires them together. **BLOCKS the service in Phase 5.**

- [ ] T011 [P] Create `backend/app/services/guardrail_rules.py` with the pattern/lexicon/regex sources: `INJECTION_PATTERNS` (override/role-switch: "ignore (all )?previous instructions", "disregard the above", "forget your instructions", "you are now", "act as … system/developer/admin", leading `system:`/`developer:`), `DISCLOSURE_PATTERNS` ("show/reveal/print/repeat your (system) prompt/hidden rules/instructions/internal policy"), `SECRET_PATTERNS` (JWT `eyJ…\.…\.…`, `sk-…`, `AKIA…`, `api_key|secret|password|bearer = …`), `UNSAFE_LEXICON` + `COMMITMENT_MARKERS` ("guaranteed refund", "i promise", "definitely free", abusive terms), `EMAIL_RE`, `PHONE_RE` (international `+961…` + local formats) — per data-model.md / plan.md
- [ ] T012 [P] Implement the detectors in `backend/app/services/guardrail_rules.py`: `detect_injection(text)`, `detect_disclosure(text)`, `detect_cross_tenant(text, tenant_registry)` (returns the matched other-tenant marker or None; registry excludes the caller tenant), `detect_secret(text)`, `detect_unsafe(text)`; all operate on `text[:GUARDRAIL_MAX_SCAN_CHARS]` and **target intent, not topic words** — "refund/policy/cancel/price/availability" alone never match (research.md Decision 12, FR-014, AC-20) (depends on T011)
- [ ] T013 [P] Create `backend/app/services/guardrail_redaction.py`: `redact_pii(text) -> (redacted, found)` (email→`[EMAIL_REDACTED]`, phone→`[PHONE_REDACTED]`, stable placeholders); `redact_text(text) -> (clean, flags)` (PII + `SECRET_PATTERNS`→`[SECRET_REDACTED]` + system-prompt-marker stripping); `redact_metadata(meta) -> dict` (drop forbidden keys: token/secret/password/api_key/authorization/jwt/prompt/target_tenant/other_tenant). Never emit raw PII/secret/prompt/cross-tenant data (FR-008, FR-019, PR-01..PR-05, SR-08) (depends on T011)
- [ ] T014 [P] Create `backend/app/services/guardrail_grounding.py`: `GroundingResult(grounded: bool, source_document_ids: list, partial: bool)` + `validate_rag_grounding(draft_text, sources) -> GroundingResult`. No sources ⇒ `grounded=False` (GR-02); else a claim-coverage heuristic (lexical/semantic overlap ≥ `GUARDRAIL_GROUNDING_THRESHOLD`) sets `grounded`; an uncovered novel claim sets `partial=True` (GR-01, GR-04, GR-05); record matched `source_document_ids` (ids only, GR-06); sources are always the caller tenant's (GR-03) (research.md Decision 4)

**Checkpoint**: Detection, redaction, and grounding are pure functions ready to unit-test (Phase 11) and to be composed by the service.

---

## Phase 5: Guardrail Service — Two Chokepoints (Foundational — Blocking)

**Purpose**: The single `GuardrailService` with `check_user_input` (before RAG/generation) and `check_ai_output` (after generation, before display), the decision builder (redact → persist → best-effort audit), the fail-safe wrappers, the most-severe-wins pipeline, the no-side-effects guarantee, and the tenant-scoped role-gated read functions. **BLOCKS the API in Phase 8 and the reply-path wiring in Phase 7.**

- [ ] T015 Implement the `_decide(...)` decision builder in `backend/app/services/guardrail_service.py`: run `redact_text` over `reason`/`redacted_text` and `redact_metadata` over `metadata`, build + flush a `GuardrailDecision` (category/action/severity/refs), then call the best-effort audit (T024); return a `CheckResult`. The decision persists even if the audit fails; **every** stored field is redacted (FR-011, FR-019, PR-02, SR-08, research.md Decisions 9 & 10) (depends on T006, T010, T013)
- [ ] T016 [US1] Implement `check_user_input(session, *, tenant_id, user_id, role, text, message_id=None) -> CheckResult` in `backend/app/services/guardrail_service.py`: cap to `GUARDRAIL_MAX_SCAN_CHARS`; empty/whitespace → `allow` (proceed, not persisted); pipeline (most-severe-wins, all `security`) `detect_injection` → `prompt_injection` refuse (`guardrail_refusal`), `detect_disclosure` → `system_prompt_disclosure` refuse (`guardrail_refusal`), `detect_cross_tenant` → `cross_tenant_access` refuse (`cross_tenant_access_blocked`, **no target id/name in metadata**); otherwise `allow` (proceed). Each refuse builds a decision via `_decide` and returns `proceed=False` + a professional `display_text` (FR-001, FR-002, FR-003, FR-004, FR-005, FR-020, AC-02, AC-03, AC-04, SR-03) (depends on T012, T015)
- [ ] T017 [US2] Implement `check_ai_output(session, *, tenant_id, user_id, draft_text, sources, source_document_ids, message_id, suggested_reply_id) -> CheckResult` in `backend/app/services/guardrail_service.py`: pipeline `validate_rag_grounding` → not grounded ⇒ `unsupported_answer` refuse (`unsupported_answer_refused`, metadata `grounded:false` + `source_document_ids`); `detect_secret`/`detect_disclosure` ⇒ `secret_or_token_exposure` refuse/redact (`guardrail_refusal`, `redacted_text` via `redact_text`); `detect_unsafe` ⇒ `unsafe_or_unprofessional_reply` `require_human_review` (held, `guardrail_refusal`); `grounding.partial` ⇒ `unsupported_answer` `require_human_review` (held); else apply `redact_pii` to the summary and `allow` (return the draft as `display_text`, still Spec 010 human-approve). Most-severe-wins; a `refuse` short-circuits display (FR-001, FR-002, FR-006, FR-007, FR-009, FR-010, GR-01..GR-06, AC-05..AC-08, research.md Decision 10) (depends on T012, T013, T014, T015)
- [ ] T018 [US1][US2] Add the fail-safe wrappers in `backend/app/services/guardrail_service.py`: wrap `check_user_input` so a probe-class internal error returns `refuse` (`human_review_required`, `proceed=False` — AI not invoked); wrap `check_ai_output` so any internal error returns `require_human_review` (`proceed=False`, draft **held**, never shown). Never fail open (FR-018, SR-05, AC-19, research.md Decision 3) (depends on T016, T017)
- [ ] T019 No-side-effects guarantee: ensure `backend/app/services/guardrail_service.py` imports/calls **no** reply-send, task (011), or escalation (012) code path; the strongest action is `require_human_review`. Add a code-level assertion/comment and back it with the Phase 11 test (FR-015, SR-06, AC-18, research.md Decision 1) (depends on T016, T017)
- [ ] T020 [US3] Implement `list_guardrail_decisions(session, tenant_id, filters: GuardrailDecisionFilters, *, limit, offset) -> (rows, total)` in `backend/app/services/guardrail_service.py`: `WHERE tenant_id` (SR-01) + optional category/action/severity/message_id/created_from/created_to; order `created_at DESC, id DESC`; `limit = min(limit, GUARDRAIL_DECISIONS_MAX_LIMIT)` (FR-016, AC-13, data-model.md) (depends on T006)
- [ ] T021 [US3] Implement `get_guardrail_decision(session, tenant_id, decision_id) -> GuardrailDecision` in `backend/app/services/guardrail_service.py`: load row; `NotFoundError` (404 `GUARDRAIL_DECISION_NOT_FOUND`) if absent; `ForbiddenError` (403 `CROSS_TENANT_FORBIDDEN`) if in another tenant — mirroring Specs 005–013 (FR-016, FR-017, AC-14) (depends on T006)
- [ ] T022 [US3] Implement `decisions_for_message(session, tenant_id, message_id, *, staff_view=False) -> (rows, total)` in `backend/app/services/guardrail_service.py`: resolve the message in-tenant (404/403 via a `_resolve_message_or_raise` helper mirroring 005–013); return decisions `WHERE tenant_id AND message_id ORDER BY created_at DESC, id DESC`; gated by `GUARDRAIL_STAFF_MESSAGE_VIEW_ENABLED` for staff (FR-016, AC-15) (depends on T006)

**Checkpoint**: Both chokepoints return `CheckResult`; decisions are built/redacted/persisted with best-effort audit; fail-safe holds output / refuses probe input on error; no auto-send/task/escalate; reads are tenant-scoped + role-aware.

---

## Phase 6: Audit-Log Integration (Spec 013, best-effort)

**Purpose**: Map each non-trivial decision to a Spec 013 audit event, passing a redacted summary; never let an audit failure break a guardrail.

- [ ] T023 Define the decision→event mapping in `backend/app/services/guardrail_service.py`: `prompt_injection`/`system_prompt_disclosure`/`secret_or_token_exposure`/`unsafe_or_unprofessional_reply` → `guardrail_refusal`; `cross_tenant_access` → `cross_tenant_access_blocked` (via `log_cross_tenant_blocked`, in the **caller's** tenant, no target data); `unsupported_answer` → `unsupported_answer_refused` (FR-012, AC-04, AC-05, AC-12)
- [ ] T024 Implement `_write_audit(session, tenant_id, message_id, event, category, redacted_meta)` in `backend/app/services/guardrail_service.py`: call Spec 013 `AuditService.log_event` / `log_cross_tenant_blocked` with a **redacted** summary (PII/secret/prompt-free; 013 redactor is the backstop) and metadata carrying only category/action/`source_document_ids`/`attempted_route` — never refused text, secret, prompt, or cross-tenant data; **best-effort**: catch and swallow any audit error so the decision still stands (FR-012, PR-06, SR-03, AC-12, research.md Decision 8) (depends on T023, T015)

**Checkpoint**: Every persisted decision attempts a redacted Spec 013 audit log; cross-tenant blocks log in the attacker's tenant only; audit failure never undoes a refuse.

---

## Phase 7: Reply-Path Wiring (Specs 009 → 010 integration)

**Purpose**: Bracket the existing 009→010 generation path with the two chokepoints so there is no path to the model/retriever that skips the input check and no path to staff that skips the output check. This feature does **not** generate replies or retrieve documents — it wraps them.

- [ ] T025 [US1] Wire `check_user_input` **before** RAG/generation in `backend/app/services/reply_service.py` (Spec 010): on the client message text (003) and any free-text staff query (FR-020); if `proceed=False` (`refuse`), short-circuit — do **not** call RAG or the model — and return the refusal payload (`display_text` + decision ref) to the caller (FR-002, AC-02, AC-06, research.md Decision 1) (depends on T016)
- [ ] T026 [US2] Wire `check_ai_output` **after** generation and **before** returning the draft in `backend/app/services/reply_service.py`: pass the draft + the Spec 009 retrieved `sources`/`source_document_ids`; apply the returned action — `allow`/`redact` → return the (redacted) draft, `require_human_review` → return the held draft + flag, `refuse` → return the professional refusal (not the draft). The Spec 010 human-approve step still applies; **never auto-send** (FR-002, FR-013, AC-06, AC-21, SR-06) (depends on T017)
- [ ] T027 Wire the Spec 009 no-source path in `backend/app/services/rag_service.py` (or at the 010 call site): when RAG reports `rag_no_source_found`, route straight to the `unsupported_answer` refusal via `check_ai_output` with empty `sources` (skip fabricating an answer) (FR-006, GR-02, AC-05) (depends on T017, T003)

**Checkpoint**: The reply path calls the input check before any RAG/model call and the output check before any draft reaches staff; no-source → unsupported refusal; no bypass; no auto-send.

---

## Phase 8: API Endpoints

**Purpose**: Expose the optional check endpoints (same in-process logic) + the read surface with the role matrix and error→HTTP mapping. A guardrail **refuse** is a normal **200**. `tenant_id`/`user_id`/`role` always from the JWT; client-supplied tenant ignored. **No create/update/delete routes for decisions (append-only → 405).**

- [ ] T028 [P] Implement `POST /api/guardrails/check-input` in `backend/app/api/v1/guardrails.py`: `require_role("staff", "manager")` (+ optional service credential); validate `CheckInputRequest`; resolve `message_id` in-tenant if present (404/403); call `service.check_user_input`; return `CheckResult` **200** for both `allow` and `refuse`; `text` invalid → 422 (contracts §1, FR-001, AC-02) (depends on T016)
- [ ] T029 [P] Implement `POST /api/guardrails/check-output` in `backend/app/api/v1/guardrails.py`: `require_role("staff", "manager")` (+ optional service credential); validate `CheckOutputRequest`; resolve `message_id`/`suggested_reply_id` in-tenant if present (404/403); call `service.check_ai_output`; return `CheckResult` **200** for `allow`/`redact`/`refuse`/`require_human_review`; `draft_text` invalid → 422 (contracts §2, FR-001, AC-05) (depends on T017)
- [ ] T030 [US3] Implement `GET /api/messages/{message_id}/guardrail-decisions` in `backend/app/api/v1/guardrails.py`: `require_role("staff", "manager")` (Platform Admin → 403); call `service.decisions_for_message`; return `MessageGuardrailDecisionsResponse` (`message_id`, `items`, `total`) **200**; cross-tenant message → 404/403 (contracts §3, FR-016, AC-15) (depends on T022)
- [ ] T031 [US3] Implement `GET /api/guardrail-decisions` in `backend/app/api/v1/guardrails.py`: `require_role("manager")` (staff/Platform Admin → 403 `INSUFFICIENT_ROLE`); parse + validate `GuardrailDecisionFilters` + `limit`/`offset`; call `service.list_guardrail_decisions`; return `GuardrailDecisionListResponse` **200**; invalid enum/date/pagination → 422 (contracts §4, FR-016, AC-13, AC-22) (depends on T020)
- [ ] T032 [US3] Implement `GET /api/guardrail-decisions/{decision_id}` in `backend/app/api/v1/guardrails.py`: `require_role("manager")` (staff/Platform Admin → 403); call `service.get_guardrail_decision`; return full **redacted** `GuardrailDecisionResponse` **200**; missing → 404 `GUARDRAIL_DECISION_NOT_FOUND`, cross-tenant → 403 `CROSS_TENANT_FORBIDDEN` (contracts §5, FR-016, AC-14, AC-17) (depends on T021)
- [ ] T033 Mount the guardrails router at `/api` in `backend/app/main.py`; confirm **no** PATCH/PUT/DELETE/POST-create route exists for `/api/guardrail-decisions` (append-only → any such method returns 405) (contracts §"No Write/Mutate Endpoints", plan.md #9) (depends on T028–T032)

**Checkpoint**: Check endpoints return 200 with a `CheckResult` (allow or refuse); read endpoints enforce the role matrix + tenant resolution; decisions are append-only (405 on mutate). Backend MVP complete.

---

## Phase 9: Frontend Integration

**Purpose**: Surface the professional refusal/hold/redact states in the reply flow, a manager decisions dashboard, a redacted decision detail, and a per-message Guardrails panel. **No** edit/delete or "reveal blocked content" controls anywhere.

- [ ] T034 [P] Add TS types to `frontend/src/types/guardrails.ts`: `GuardrailCategory`, `GuardrailAction`, `GuardrailSeverity`, `GuardrailDecision`, `CheckResult` (data-model.md Frontend Types)
- [ ] T035 [P] Add the typed API client `frontend/src/api/guardrails.ts`: `checkInput(text, messageId?)`, `checkOutput(payload)`, `listGuardrailDecisions(filters, page)`, `getGuardrailDecision(id)`, `decisionsForMessage(messageId)` — calling the endpoints with the auth header (depends on T034)
- [ ] T036 [P] Implement category/action/severity badge components in `frontend/src/components/guardrails/` (e.g. `GuardrailSeverityBadge.tsx`, `GuardrailActionBadge.tsx`, category chip): colored badges per enum value incl. the `security` severity (AC-13) (depends on T034)
- [ ] T037 [US1][US2] Implement `frontend/src/components/guardrails/GuardrailRefusalBanner.tsx`: the staff-facing professional refusal/hold/redact message used in the reply flow — `refuse` → refusal banner (e.g. "This can't be answered from your business documents — please confirm with the client."), `require_human_review` → held draft + "needs review" badge, `redact` → redacted draft + redaction indicator. Never render the offending output/prompt/secret/cross-tenant data (FR-013, AC-21, research.md Decision 11) (depends on T034)
- [ ] T038 [US1][US2] Integrate the banner into the reply UI on `frontend/src/pages/ConversationDetailPage` (Spec 005 / 010): consume the reply-path `CheckResult` — show `GuardrailRefusalBanner` instead of the draft when refused, the held draft + review badge when `require_human_review`, the redacted draft when `redact`, the normal (human-approve) draft when `allow`; no "reveal" control (FR-013, AC-21) (depends on T037)
- [ ] T039 [US3] Implement `frontend/src/components/guardrails/GuardrailDecisionRow.tsx` + `GuardrailDecisionTable.tsx`: newest-first table with time, category chip, action badge, severity badge, message link, reason; empty state (plan.md Frontend #5, AC-13) (depends on T035, T036)
- [ ] T040 [US3] Implement `frontend/src/components/guardrails/GuardrailDecisionFilters.tsx` + `GuardrailDecisionsPage.tsx` at route `/guardrail-decisions` (manager-only): the dashboard listing tenant decisions via the table with category/action/severity/date-range/message filters + pagination; loading/empty/error (422 inline, 403 role/cross-tenant) states; register the route in `frontend/src/App.tsx` and add a Guardrails nav item (manager) (plan.md Frontend #4, AC-13, AC-22) (depends on T039)
- [ ] T041 [US3] Implement `frontend/src/components/guardrails/GuardrailDecisionDetail.tsx`: a read-only drawer showing category/action/severity/reason/`redacted_text`/`metadata`/refs for a single decision; **no** edit/delete/reveal controls (plan.md Frontend #6, AC-14, AC-17) (depends on T035, T036)
- [ ] T042 [US3] Add a "Guardrails" panel to the message detail page (Spec 005) showing `decisionsForMessage` (staff-visible per `GUARDRAIL_STAFF_MESSAGE_VIEW_ENABLED`) so staff understand a refusal/hold; loading/empty/error states (plan.md Frontend #8, AC-15, AC-21) (depends on T035, T036)

**Checkpoint**: The reply flow shows a professional refusal/hold/redact state (never the offending output); the manager dashboard lists + filters + opens redacted decisions; the message panel explains refusals to staff; no edit/delete/reveal affordances exist.

---

## Phase 10: Tenant Isolation & Role Security Tests (cross-cutting)

**Purpose**: Prove Tenant A never reads/affects Tenant B decisions/messages, `tenant_id`/`user_id`/`role` come only from the JWT, the role matrix holds, and decisions are append-only. `backend/tests/integration/test_guardrails.py`.

- [ ] T043 [P] Tenant isolation on list: decisions created in A and B → listing as A's manager returns only A's (B absent) (AC-13, AC-16)
- [ ] T044 [P] Tenant A cannot read a Tenant B decision: `GET /api/guardrail-decisions/{B_id}` as A's manager → 404/403 `CROSS_TENANT_FORBIDDEN`; no data exposed (AC-14, AC-16)
- [ ] T045 [P] Tenant A cannot query a Tenant B message's decisions: `GET /api/messages/{B_message}/guardrail-decisions` as A → 404/403 (AC-15, AC-16)
- [ ] T046 [P] Role matrix: `staff` calling `GET /api/guardrail-decisions` or `GET /api/guardrail-decisions/{id}` → 403 `INSUFFICIENT_ROLE`; staff CAN call the check endpoints + `GET /api/messages/{id}/guardrail-decisions` for their own message (contracts Role Matrix, AC-22, SR-07)
- [ ] T047 [P] Platform Admin → 403 `INSUFFICIENT_ROLE` on **all** guardrail endpoints (check-input, check-output, message-decisions, list, get); unauthenticated → 401 on each (AC-22, SR-07)
- [ ] T048 [P] Client-supplied `tenant_id` ignored: a `tenant_id` injected into a check/read body or query does not change scope — decisions persist under and reads filter by the JWT tenant only (SR-01, FR-017)
- [ ] T049 [P] Cross-tenant probe stores no target data: a `cross_tenant_access` decision + its `cross_tenant_access_blocked` audit (in the caller's tenant) contain no other-tenant name/id in `reason`/`redacted_text`/`metadata` (SR-03, AC-04, AC-17)
- [ ] T050 [P] Append-only: `PATCH`/`PUT`/`DELETE /api/guardrail-decisions/{id}` and `POST /api/guardrail-decisions` → 405 `METHOD_NOT_ALLOWED` (no route); no decision is ever mutated/deleted (contracts §"No Write/Mutate Endpoints")

**Checkpoint**: Tenant isolation, the role matrix, client-tenant-ignored, no-target-data, and append-only are all proven.

---

## Phase 11: Guardrail Behaviour Tests (unit + integration)

**Purpose**: Verify detection precision (incl. benign negatives), redaction, grounding, fail-safe, no-side-effects, the two chokepoints, and all behavioural acceptance criteria. `backend/tests/unit/` + `backend/tests/integration/test_guardrails.py`.

- [ ] T051 [P] Unit `backend/tests/unit/test_guardrail_rules.py`: `detect_injection`/`detect_disclosure`/`detect_cross_tenant`/`detect_secret`/`detect_unsafe` catch the probes AND the critical **benign-topic negatives** — "what's your refund policy?", "can we cancel?", "send pricing" → no match (AC-02, AC-03, AC-04, AC-20, research.md Decision 12)
- [ ] T052 [P] Unit `backend/tests/unit/test_guardrail_redaction.py`: `redact_pii` on the Example-4 string → "Client provided contact details [EMAIL_REDACTED], [PHONE_REDACTED]." (international `+961…` + local formats); `redact_text` strips JWT/`sk-…`/`AKIA…`/key=secret; `redact_metadata` drops forbidden keys; assert **no** forbidden content remains (AC-09, AC-17, PR-02, PR-04)
- [ ] T053 [P] Unit `backend/tests/unit/test_grounding.py`: no sources ⇒ `grounded=False` (GR-02); faithful paraphrase of a source ⇒ `grounded=True` (GR-04); some grounded + one invented claim ⇒ `partial=True` (GR-05); `source_document_ids` recorded, no document text (GR-06) (AC-05)
- [ ] T054 [P] Unit `backend/tests/unit/test_guardrail_service.py`: fail-safe — forcing `check_ai_output` to raise → `require_human_review` (`proceed=False`, draft held); forcing the input probe path to raise → `refuse` (`proceed=False`, AI not invoked); no-side-effects — the service path calls no send/task(011)/escalation(012) code (AC-18, AC-19, SR-05, SR-06)
- [ ] T055 [P] Integration: normal pricing message → `check_user_input` `allow` + RAG/draft proceeds (AC-01); a topical "refund policy" message → `allow` (AC-20) (depends on T028, T025)
- [ ] T056 [P] Integration: prompt-injection input → `prompt_injection` `refuse` (security), AI not invoked, **no** hidden rules in `reason`/`display_text`, `guardrail_refusal` audit written (AC-02) (depends on T028, T024)
- [ ] T057 [P] Integration: system-prompt-disclosure input → `system_prompt_disclosure` `refuse` (security); response contains no prompt/policy/secret text (AC-03)
- [ ] T058 [P] Integration: cross-tenant request (by name and by id) as A → `cross_tenant_access` `refuse`, no B source retrieved, `cross_tenant_access_blocked` audit **in A**, no B data in the decision (AC-04, SR-02, SR-03)
- [ ] T059 [P] Integration: ungrounded/no-source draft → `unsupported_answer` `refuse`/`require_human_review`, safe "not in your documents" `display_text`, `unsupported_answer_refused` audit; a grounded paraphrase (sources provided) → `allow` (AC-05) (depends on T029, T027)
- [ ] T060 [P] Integration: output check runs **after** generation and **before** display — assert the check precedes the draft being returned and an unchecked draft is never returned (AC-06) (depends on T026)
- [ ] T061 [P] Integration: a draft containing a JWT/API-key/secret → `secret_or_token_exposure` `refuse`/`redact`, secret never in the response; a rude/unauthorized-commitment draft → `unsafe_or_unprofessional_reply` `require_human_review`/`refuse` (AC-07, AC-08)
- [ ] T062 [P] Integration: PII in a message → `redact`/`info`, `proceed=true` (not blocked); the decision/audit summary uses `[EMAIL_REDACTED]`/`[PHONE_REDACTED]`; the original stored message body (003) is unchanged (AC-09, AC-10, PR-01, PR-03)
- [ ] T063 [P] Integration: each non-trivial evaluation persists a `GuardrailDecision` with category/action/severity/reason/refs/metadata (AC-11); the audit is best-effort — injecting an audit failure still leaves the decision persisted and the refuse standing (AC-12) (depends on T024)
- [ ] T064 [P] Integration: manager list filters (category/action/severity/date/message) return correct in-tenant subsets newest-first + paginated (AC-13); get one returns the full redacted decision (AC-14); message-scoped read works for staff on their message (AC-15) (depends on T030, T031, T032)
- [ ] T065 [P] Integration: redaction over representative decisions — no system prompt/secret/JWT/API key/raw PII/cross-tenant data in any decision field or audit summary (AC-17); 422 on invalid filter/pagination/payload, 401 unauth, 403/404 role/cross-tenant (AC-22)

**Checkpoint**: All 22 acceptance criteria are covered by passing unit/integration tests; detection precision, redaction, grounding, fail-safe, two-chokepoints, best-effort audit, and no-side-effects verified.

---

## Phase 12: Frontend Tests

**Purpose**: Render/interaction tests for the refusal/hold/redact banner, the decisions dashboard + filters, the redacted detail, the message panel, and the absence of edit/delete/reveal controls.

- [ ] T066 [P] `GuardrailRefusalBanner` test in `frontend/src/components/guardrails/__tests__/GuardrailRefusalBanner.test.tsx`: refusal message renders for `refuse`; "needs review" badge for `require_human_review`; redaction indicator for `redact`; the offending output is never rendered (AC-21)
- [ ] T067 [P] `GuardrailDecisionTable`/`GuardrailDecisionsPage` test: renders tenant decisions with category/action/severity badges + message link + reason; filters drive the query; empty + loading + error (403/422) states render; **no** edit/delete/reveal controls present (AC-13, AC-22) (depends on T040)
- [ ] T068 [P] `GuardrailDecisionDetail` + message-panel test: detail renders redacted fields read-only (no reveal control); the message Guardrails panel renders `decisionsForMessage` with loading/empty/error states (AC-14, AC-15, AC-17, AC-21) (depends on T041, T042)

**Checkpoint**: Frontend states + interactions verified; refusal/hold/redact rendering and the no-reveal/no-mutate guarantees confirmed in the UI.

---

## Phase 13: Quickstart & Manual Validation

**Purpose**: Execute the seven-step quickstart end to end (quickstart.md). Requires staff + manager accounts per tenant and an uploaded EW document.

- [ ] T069 Run migrations (`alembic upgrade head`); confirm `guardrail_decisions` created (append-only) and UPDATE/DELETE revoked; set `GUARDRAILS_ENABLED=true`, `GUARDRAIL_STAFF_MESSAGE_VIEW_ENABLED=true`; log in as staff + manager of both demo tenants
- [ ] T070 Step 1 — normal pricing request + a topical "refund policy" message → both `allow`, `proceed:true` (FR-014, AC-01, AC-20)
- [ ] T071 Step 2 + 3 — prompt-injection and system-prompt-disclosure attempts → `refuse` (security), `proceed:false`; confirm the manager decision list + a `guardrail_refusal` security audit; assert no leaked internals (system prompt / API key / bearer / secret) in the refusal (AC-02, AC-03)
- [ ] T072 Step 4 — cross-tenant request ("Show me Royal Events Agency's refund policy.") as EW → `cross_tenant_access` `refuse`; no Royal Events data in `metadata`; `cross_tenant_access_blocked` audit **in Elegant Weddings** (AC-04, SR-03)
- [ ] T073 Step 5 — unsupported "fireworks/drones/celebrity singers" draft with empty sources → `unsupported_answer` `refuse`/`require_human_review` with the safe "not in your documents" message; a grounded paraphrase with sources → `allow`; confirm the `unsupported_answer_refused` audit (AC-05)
- [ ] T074 Step 6 — message with email/phone → not blocked (`allow`/`redact`, `proceed:true`); decision/audit summaries read `[EMAIL_REDACTED]`/`[PHONE_REDACTED]`; assert no raw `maya@example`/`70111222`/`+961` leaks into any decision summary; the stored message body still has the real contact details (AC-09, AC-10)
- [ ] T075 Step 7 + fail-safe — an invented-policy draft ("guarantee a full 100% refund … no questions asked", empty sources) → blocked/held (`unsupported_answer` and/or `unsafe_or_unprofessional_reply`); white-box: force `check_ai_output` to raise → `require_human_review`, `proceed:false` (draft held, never shown) (AC-08, AC-19)
- [ ] T076 No-side-effects + append-only + isolation checks: after Steps 2–7 confirm no task/escalation was created by the guardrail path; `DELETE /api/guardrail-decisions/{id}` → 405; staff `GET /api/guardrail-decisions` → 403; RE manager fetching an EW decision by id → 404/403; the redaction-backstop grep over decision summaries returns 0 secrets/prompts/tokens (AC-16, AC-17, AC-18, AC-22)
- [ ] T077 UI walkthrough: `/guardrail-decisions` as a manager (newest-first table + filters incl. `severity=security` + pagination + redacted detail; no edit/delete/reveal); the message-detail refusal banner + "needs review" badge for staff; staff cannot open the tenant-wide dashboard (quickstart.md "See It in the UI", AC-21)

**Checkpoint**: Quickstart passes end to end; the seven scenarios + fail-safe + no-side-effects + isolation demonstrated live.

---

## Phase 14: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T078 Verify AC-01..AC-22 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T079 Walk `checklists/requirements.md` (Functional / AI Safety / RAG Grounding / PII Redaction / Security / Tenant Isolation / Audit-Log Integration / API-Service / Data / Testing) and tick each implemented item; confirm the six hard guarantees (two chokepoints, fail-safe, redaction-everywhere, tenant isolation, no autonomous side effects, never blocks valid messages)
- [ ] T080 Confirm Out-of-Scope items remain **unbuilt**: no auto-sending replies (Spec 010 human-approve preserved); no creating tasks (011) or escalations (012) in this feature; no real WhatsApp API / outbound messaging; no calendar syncing / full CRM; no per-message guardrail disable/override or "reveal blocked content" toggle; no trained ML classifier / external moderation API (rules/heuristics only); no editing/deleting decisions (append-only); no exposing system prompts/secrets/tokens/keys/hidden instructions; no cross-tenant retrieval or metadata leakage; no unsupported answers presented as ready replies; no retention/export/SIEM/alerting (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 014 verified against spec + checklist; the safety/trust layer wraps the 009→010 loop with input/output chokepoints, persists redacted append-only decisions, writes best-effort Spec 013 audit logs, fails safe, and never auto-sends/creates/escalates — while letting normal valid messages through.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (DB/model + append-only)** → depends on Phase 1; **BLOCKS everything**.
- **Phase 3 (Enums/schemas)** → depends on Phase 1; blocks Phases 4–8.
- **Phase 4 (Rules/redaction/grounding)** → depends on Phase 3; pure functions; blocks the service.
- **Phase 5 (Service — two chokepoints)** → depends on Phases 2–4; **BLOCKS the API + reply-path wiring**.
- **Phase 6 (Audit integration)** → folded into the decision builder (T015); depends on Phase 5; best-effort.
- **Phase 7 (Reply-path wiring 009/010)** → depends on Phase 5 (consumes `check_user_input`/`check_ai_output`).
- **Phase 8 (API)** → depends on Phase 5; **MVP backend deliverable**.
- **Phase 9 (Frontend)** → depends on Phase 8 (reads) + Phase 7 (the reply-flow `CheckResult` for the banner).
- **Phase 10 (Isolation/role tests)** + **Phase 11 (Behaviour tests)** → depend on Phases 5–8.
- **Phase 12 (Frontend tests)** → depends on Phase 9.
- **Phase 13 (Quickstart)** → depends on Phases 7–9.
- **Phase 14 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3 — input check, output check, decisions read surface)

1. Phase 1: Setup (config + RAG/draft accessors + demo data)
2. Phase 2: DB + model + migration + append-only revocation (**CRITICAL**)
3. Phase 3: Enums + schemas
4. Phase 4: Rules + redaction + grounding (unit-tested in isolation)
5. Phase 5: Service (decision builder → `check_user_input` → `check_ai_output` → fail-safe → reads → no-side-effects)
6. Phase 6 + 7: best-effort audit + wire the two chokepoints into the 009→010 reply path
7. Phase 8: API (check endpoints + read endpoints + router mount; append-only 405)
8. **STOP and VALIDATE**: run isolation + behaviour tests; confirm two chokepoints, fail-safe, redaction-everywhere, tenant isolation, no auto-send/task/escalate, and that normal valid messages pass

### Incremental Delivery

1. Setup + DB + schemas + rules/redaction/grounding → foundation ready
2. US1 (input chokepoint: injection/disclosure/cross-tenant refused before RAG/generation) → unsafe inputs never reach the model
3. US2 (output chokepoint: grounding/unsupported/secret/unsafe checked before display; PII-redacted summaries) → hallucinations/leaks never reach staff
4. US3 (decisions persisted + manager dashboard + message-scoped staff panel + best-effort audit) → oversight + transparency
5. US4 (PII redaction in logs/summaries — P2) → privacy minimization on the oversight surface
6. Frontend → refusal/hold/redact banner in the reply flow + decisions dashboard + filters + redacted detail + message panel
7. Tests + quickstart + acceptance → all 22 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id`/`user_id`/`role` are **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SR-01, FR-017); any client-supplied `tenant_id` is ignored (T048)
- **Two chokepoints** — `check_user_input` runs before RAG/generation, `check_ai_output` runs before display; the reply-path wiring (T025–T027) is the only generation path and it cannot skip either check (FR-002, AC-06, research.md Decision 1). First hard guarantee
- **Fail safe, not open** — an output-check error holds the draft (`require_human_review`); an input probe-class error refuses (AI not invoked); the safe state is never "show/run the unchecked thing" (FR-018, SR-05, AC-19, T018, T054). Second hard guarantee
- **Redaction in every stored field** — `redact_text`/`redact_metadata` run at the single decision-builder boundary (T015) over `reason`/`redacted_text`/`metadata` + the audit summary, with the Spec 013 redactor as backstop; a refusal stores only the category + short reason, never the offending payload (FR-019, PR-02, PR-05, SR-08, research.md Decision 9). Third hard guarantee
- **Tenant isolation** — every read/write filters by `tenant_id`; retrieval stays tenant-scoped server-side (the hard boundary, SR-02); `cross_tenant_access` decisions/audits store no target-tenant data and log in the caller's tenant only (SR-03, T049); no other-tenant document is ever retrieved for grounding (GR-03). Fourth hard guarantee
- **No autonomous side effects** — the guardrail path never auto-sends a reply, creates a task (011), or escalates (012); the strongest action is `require_human_review`, on which a human acts via Specs 010/011/012 (FR-015, SR-06, AC-18, T019, T054). Fifth hard guarantee
- **Never blocks valid messages** — detection targets intent (override/disclosure/cross-tenant/fabrication/secret), not topic words; "refund/policy/cancel/price/availability" pass; PII → `redact` (info), never `refuse` (FR-014, FR-008, AC-01, AC-20, PR-03, research.md Decision 12, T051). Sixth hard guarantee
- **Append-only decisions** — like Spec 013 audit logs: no `updated_at`, no PATCH/PUT/DELETE/create route (→405), DB-level UPDATE/DELETE revocation recommended (T008, T050)
- **Most-severe-wins, one decision per check** — each check returns a single `GuardrailDecision` at the most severe finding; secondary findings go in `metadata.also_flagged`; PII redaction of summaries is always applied regardless of the headline action (research.md Decision 10)
- **Best-effort audit** — a `refuse` stands even if the Spec 013 audit (or its summary) fails; the audit is the record, the block is the behaviour (FR-012, AC-12, research.md Decision 8, T024)
- **Grounded-only answers** — a shown draft's factual claims must be supported by retrieved tenant sources; no-source / ungrounded ⇒ `unsupported_answer` refuse/hold; faithful paraphrase passes, invention fails, partial grounding ⇒ at least review (GR-01..GR-06, research.md Decision 4)
- **Detection is rule/heuristic-based in the MVP** — pattern lists + grounding/no-source checks + PII regex; no trained classifier or external moderation API (spec Out of Scope, research.md Decision 2)
- A guardrail **refuse** is a normal **200** carrying a `CheckResult`, not an HTTP error (contracts §intro); the check endpoints run the **same** in-process logic as the reply path, not a second code path
- **PII redaction minimizes logs/summaries, not the stored message** — the Spec 003 message body is untouched; only guardrail summaries/`redacted_text` and Spec 013 audit summaries use placeholders (PR-01, AC-10, research.md Decision 6)
- This feature **wraps** the 009→010 path and writes Spec 013 audit logs; it does not generate replies, retrieve documents, create tasks, or escalate — those remain owned by Specs 009/010/011/012
