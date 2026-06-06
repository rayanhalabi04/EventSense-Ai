# Requirements Checklist: Suggested Replies

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (human-reviewed grounded replies) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI behavior, RAG grounding, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Generation uses message text + intent (006) + risk (007) + RAG sources (009) (FR-001)
- [ ] Each draft stored as `SuggestedReply` linked to its message, status `draft_generated`, with model_name/prompt_version/timestamps (FR-002)
- [ ] Grounded drafts record source_document_ids + source_chunk_ids and show references (FR-003)
- [ ] Staff can edit a draft → `edited_text` stored, `generated_text` preserved, status `edited` (FR-006, AC-06)
- [ ] Staff/manager can approve → status `approved`, approved_by + approved_at recorded (FR-007, AC-07)
- [ ] Staff/manager can reject → status `rejected` (FR-008, AC-08)
- [ ] Invalid state transitions are rejected (FR-009, AC-09)
- [ ] Suggested reply surfaced on the message detail page (FR-011, AC-17)
- [ ] Reply is tenant-scoped via its message (FR-012, AC-10)
- [ ] Reply is professional, concise, polite (FR-014)
- [ ] Multiple generations create new rows; approved never overwritten (FR-015, AC-16)
- [ ] Generation requires upstream intent + risk + RAG; missing → precondition error (AC-18)

---

## AI Requirements

- [ ] Prompt context = message + intent + risk + tenant RAG snippets (no raw cross-tenant content)
- [ ] Exactly one draft text produced per generation call
- [ ] High-risk → careful/empathetic wording; may recommend escalation (FR-010, AC-05)
- [ ] Low-risk → professional/friendly tone
- [ ] AI never auto-sends (FR-005, SR-06, AC-15)
- [ ] AI creates no tasks and no escalations (FR-010, SR-07)
- [ ] `model_name` + `prompt_version` recorded on every draft
- [ ] Generation behind an interface (LLM in prod, deterministic stub in tests)
- [ ] Model unavailable → 503, no malformed draft stored
- [ ] Reply length bounded; concise output

---

## RAG Grounding Requirements

- [ ] Any policy/package fact comes from a retrieved source and is recorded in source ids (GR-01, AC-02)
- [ ] No supporting source (`no_source`/`no_documents`) for a policy/package question → refusal draft, no invented facts (GR-02, FR-004, AC-03)
- [ ] Refusal text states info is not in uploaded documents + recommends human review
- [ ] Only the message tenant's RAG sources may ground the reply (GR-03, FR-013, AC-11)
- [ ] Grounding context uses bounded chunk snippets, not whole documents (GR-04)
- [ ] Draft never cites a source id not in the retrieval result (GR-05)
- [ ] Stored reply records whether it is grounded or a refusal (`grounded` flag) (GR-06)
- [ ] No uncited factual claims about policy/pricing/availability (AC-04)

---

## Human Review Requirements

- [ ] Every draft requires explicit human action (no auto-approval)
- [ ] Edit preserves the original AI text separately from the human edit
- [ ] Effective text = edited_text if present else generated_text
- [ ] Approve records reviewer identity + timestamp
- [ ] Reject marks the reply unused (optional reason captured, no action)
- [ ] Terminal states (`approved`/`rejected`) are immutable for content
- [ ] Approval performs no send (human-acceptance only)
- [ ] High-risk/escalation cases are reviewable by manager

---

## Security Requirements

- [ ] `tenant_id` always derived from JWT — never from the client (SR-01)
- [ ] Reply bound to its message's tenant (SR-02)
- [ ] Generation uses only the message tenant's RAG sources (SR-03)
- [ ] Only `staff`/`manager` generate/review; Platform Admin → 403 (SR-04, AC-14)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent message/reply → 404; cross-tenant → 403 (SR-05)
- [ ] No code path sends a reply (SR-06)
- [ ] No tasks/escalations created (SR-07)
- [ ] `approved_by`, model_name, prompt_version, source ids cannot be spoofed by the client (SR-08)

---

## Tenant Isolation Requirements

- [ ] Tenant A cannot read/modify Tenant B suggested replies (AC-10)
- [ ] Draft references only the message tenant's sources (AC-11)
- [ ] Cross-tenant message/reply id → 404/403 (AC-13)
- [ ] Demo: EW pricing draft cites EW package only; RE cites RE package only
- [ ] Cross-tenant RAG sources never enter the prompt (defence-in-depth assertion before generation)
- [ ] No shared/global reply or source pool

---

## API Requirements

- [ ] `POST /api/messages/{id}/suggested-replies` generates a draft (201) (AC-01, AC-12)
- [ ] `POST` returns 409 `PRECONDITION_NOT_MET` when upstream missing (AC-18)
- [ ] `POST` returns 503 `MODEL_UNAVAILABLE` when generation fails; no draft stored
- [ ] `GET /api/messages/{id}/suggested-replies` lists drafts (newest first) (AC-12)
- [ ] `GET /api/suggested-replies/{id}` returns one reply; cross-tenant → 404/403 (AC-13)
- [ ] `PATCH /api/suggested-replies/{id}` edits non-terminal; empty text → 422; terminal → 422 (AC-06, AC-09)
- [ ] `POST .../approve` approves non-terminal; records reviewer; no send (AC-07, AC-15)
- [ ] `POST .../reject` rejects non-terminal (AC-08)
- [ ] Role matrix enforced; Platform Admin 403 everywhere (AC-14)
- [ ] Error responses use consistent `error_code` values per the contract

---

## Data Requirements

- [ ] `suggested_replies` table created via Alembic migration
- [ ] Fields: id, tenant_id, message_id, generated_text, edited_text, status, source_document_ids, source_chunk_ids, model_name, prompt_version, created_at, updated_at, approved_by, approved_at
- [ ] Plus `grounded` flag + `rag_query_id` provenance link
- [ ] `message_id` FK with `ON DELETE CASCADE`; `tenant_id` denormalised + indexed
- [ ] `SuggestedReplyStatus` enum: draft_generated, edited, approved, rejected
- [ ] `generated_text` immutable after creation; edits live in `edited_text`
- [ ] State machine enforced: terminal states immutable; only valid transitions allowed
- [ ] Indexes: `(tenant_id, message_id)`, `(message_id, created_at)`, `(tenant_id, status)`
- [ ] Source id lists stored (JSONB or uuid[]) and validated ⊆ retrieval result

---

## Testing Requirements

- [ ] Unit: prompt builder (grounded vs refusal selection, tone by risk, snippet bounding, prompt_version)
- [ ] Unit: service state machine (valid/invalid transitions, effective-text rule, cited-source ⊆ retrieval)
- [ ] Integration: grounded draft + sources (AC-01, AC-02); refusal on no source (AC-03); no uncited facts (AC-04)
- [ ] Integration: high-risk tone + no escalation/task (AC-05)
- [ ] Integration: edit (AC-06); approve + no send (AC-07); reject (AC-08); invalid transitions (AC-09)
- [ ] Integration: tenant isolation (AC-10); sources tenant-only (AC-11)
- [ ] Integration: generate+list (AC-12); get + cross-tenant (AC-13)
- [ ] Integration: Platform Admin 403 (AC-14); no send path (AC-15); multiple drafts + approved preserved (AC-16)
- [ ] Integration: precondition missing → error (AC-18)
- [ ] Frontend: panel grounded vs refusal; editor only in non-terminal; approve/reject update (AC-17)
- [ ] Eval: 5 quickstart scenarios produce expected grounded/refusal/tone/isolation outcomes

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No sending of any reply (no WhatsApp/email/SMS transport)
- [ ] No task creation
- [ ] No escalation workflow (drafts may recommend escalation only)
- [ ] No re-implementation of intent/risk/RAG (consumed from 006/007/009)
- [ ] No audit-log system (logging added by the later audit feature)
- [ ] No multi-turn/threaded generation
- [ ] No auto-approval / auto-regeneration
- [ ] No tone/style configuration UI (fixed professional tone)
- [ ] No unsupported/invented AI answers
- [ ] No cross-tenant RAG sources
- [ ] No real WhatsApp API, no calendar syncing, no full CRM

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build prompt + generator + service (with grounding/refusal + state machine) before the API.
- The two hard guarantees to verify: (1) no invented answers — refusal is a code path, not a prompt request; (2) no auto-send — there is no send path anywhere.
