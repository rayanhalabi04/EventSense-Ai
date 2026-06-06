# Feature Specification: Suggested Replies

**Feature Branch**: `010-suggested-replies`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 007 — Risk Detection](../007-risk-detection/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)

**Input**: User description: "The system should generate a professional suggested reply for a client message using the message content, intent classification, risk assessment, and tenant-scoped RAG retrieval results. The reply must be grounded in the current tenant's retrieved documents when policy or package information is needed. The AI must never auto-send the reply; a staff user must review, edit, approve, or reject it."

---

## Goal

Generate a professional, concise, polite draft reply for a client message — grounded in the current tenant's retrieved documents whenever policy or package information is needed — and present it to staff for human review. The draft combines four signals already produced upstream: the message text (Spec 003), its intent (Spec 006), its risk (Spec 007), and tenant-scoped RAG sources (Spec 009). The AI **never sends** anything: a staff user must review, edit, approve, or reject every draft. When RAG finds no supporting source for a policy/package question, the AI must **not invent** an answer — it states the information is not in the uploaded documents and recommends human review. High-risk messages get careful wording and may note that escalation is advisable (escalation itself is a separate feature). Every suggested reply is tenant-scoped through its message; Tenant A can never access Tenant B messages, sources, or replies.

---

## Suggested Reply Statuses

| Status | Meaning |
|--------|---------|
| `draft_generated` | AI produced a draft; awaiting human review |
| `edited` | A staff user modified the draft text (still not approved/sent) |
| `approved` | A staff user approved the reply (final human-accepted text) — not auto-sent |
| `rejected` | A staff user rejected the draft (will not be used) |

Sending is **out of scope**: `approved` means "human-accepted", not "sent".

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | Reviews the AI draft on the message detail page; edits the wording, approves it (human-accepted), or rejects it. The primary reviewer. |
| **Manager** | Reviews suggested replies for high-risk or escalation-recommended cases; can also edit/approve/reject. |
| **System / AI service** | Generates the draft from message + intent + risk + RAG sources, enforcing grounding and refusal rules. Not a human actor; takes no send action. |

Platform Admin has no access to tenant messages, sources, or suggested replies.

---

## User Stories

### User Story 1 — Generate a Grounded Suggested Reply (Priority: P1)

For a client message, the system generates a professional draft reply using the message text, its intent, its risk, and the tenant's RAG sources. When the question concerns policy or packages, the draft is grounded in the retrieved tenant documents and cites them. The draft is stored linked to the message with status `draft_generated`.

**Why this priority**: The draft is the feature's core output — without generation there is nothing to review. It is the step that consumes all upstream AI signals and turns them into staff-actionable text.

**Independent Test**: For an Elegant Weddings message "Can you send me your wedding package prices?" (intent `pricing_request`, RAG returns the package document), generate a reply. Verify a `SuggestedReply` is created linked to the message with status `draft_generated`, non-empty `generated_text` that references the package information, and `source_document_ids`/`source_chunk_ids` pointing at the retrieved Elegant Weddings sources.

**Acceptance Scenarios**:

1. **Given** a message with intent, risk, and grounded RAG sources, **When** generation runs, **Then** a `SuggestedReply` is stored with status `draft_generated`, non-empty `generated_text`, and `source_document_ids` + `source_chunk_ids` referencing the RAG sources used.
2. **Given** a policy/package question with grounded sources, **When** the draft is generated, **Then** the reply content is consistent with the retrieved source text and includes source references.
3. **Given** generation for a Tenant A message, **When** the reply is stored, **Then** it is scoped to Tenant A and references only Tenant A sources.
4. **Given** the AI service records provenance, **When** the draft is stored, **Then** `model_name` and `prompt_version` are recorded.

---

### User Story 2 — Refuse to Invent When No Source Supports the Answer (Priority: P1)

When a policy/package question has no supporting RAG source (RAG returned `no_source` or `no_documents`), the AI must not fabricate. The draft explicitly states the information is not available in the uploaded documents and recommends human review/confirmation.

**Why this priority**: Grounding integrity is the safety guarantee of the whole AI workflow. An invented policy could mislead a client and harm the agency. Equal priority to US1 because a generation feature that hallucinates is unacceptable to ship.

**Independent Test**: For "Can you organize fireworks with drones and celebrity singers?" where no document supports it, generate a reply. Verify the draft does **not** assert any specific policy/price/availability, instead states the service is not listed in the uploaded documents (or needs confirmation), recommends human follow-up, has empty `source_document_ids`/`source_chunk_ids`, and is flagged as ungrounded.

**Acceptance Scenarios**:

1. **Given** a policy/package question with RAG status `no_source` or `no_documents`, **When** generation runs, **Then** the draft does not state any specific policy, price, or availability and instead says the information is not in the uploaded documents and recommends human review.
2. **Given** an ungrounded draft, **When** it is stored, **Then** `source_document_ids` and `source_chunk_ids` are empty and the reply is marked as not grounded.
3. **Given** a non-policy/general message (e.g., a greeting) with no sources, **When** generation runs, **Then** a polite, generic professional reply is produced without asserting unsupported facts.
4. **Given** any draft, **When** it asserts policy/package facts, **Then** those facts are traceable to a cited source (no uncited factual claims about policy/pricing).

---

### User Story 3 — Human Review: Edit, Approve, Reject (Priority: P1)

A staff (or manager) user reviews the draft on the message detail page. They can edit the wording (stored as `edited_text`, status `edited`), approve it (status `approved`, recording who and when), or reject it (status `rejected`). Nothing is ever auto-sent.

**Why this priority**: Human-in-the-loop is a hard product requirement — the AI must never act unilaterally. Review is what makes the draft safe to use. Equal P1 because generation without mandatory human control violates the core constraint.

**Independent Test**: Take a `draft_generated` reply. Edit its text → verify `edited_text` stored and status `edited`. Approve it → verify status `approved`, `approved_by` = the user, `approved_at` set. On another draft, reject it → verify status `rejected`. Confirm no send action occurs in any path.

**Acceptance Scenarios**:

1. **Given** a draft, **When** a staff user edits the text, **Then** `edited_text` is stored, the original `generated_text` is preserved, and status becomes `edited`.
2. **Given** a draft or edited reply, **When** a staff/manager user approves it, **Then** status becomes `approved`, `approved_by` and `approved_at` are recorded, and the system performs no send.
3. **Given** a draft or edited reply, **When** a user rejects it, **Then** status becomes `rejected` and it will not be used.
4. **Given** a reply in another tenant, **When** a user attempts to edit/approve/reject it, **Then** it is blocked (404/403) and no change occurs.
5. **Given** an approved or rejected reply, **When** a user tries to edit it, **Then** the request is rejected (invalid state transition) — terminal states are immutable for content.

---

### User Story 4 — Careful Wording for High-Risk Messages (Priority: P2)

For high-risk messages (Spec 007), the draft uses careful, empathetic, de-escalating wording and may note that escalation to a manager is advisable. It does not perform escalation (separate feature).

**Why this priority**: High-risk client messages (complaints, cancellations, payment disputes) need tone control to avoid making situations worse. Lower than P1 because grounded generation + review already deliver value; tone refinement is an enhancement on top.

**Independent Test**: For a high-risk complaint ("I am very unhappy with the decoration sample and the wedding is next week"), generate a reply. Verify the draft acknowledges the concern empathetically, avoids dismissive/over-promising language, and includes a note that the case may warrant manager escalation — without triggering any escalation.

**Acceptance Scenarios**:

1. **Given** a message with risk level `high`, **When** the draft is generated, **Then** the wording is careful and empathetic and avoids commitments not supported by sources.
2. **Given** a high-risk or escalation-recommended message, **When** the draft is generated, **Then** it may include a recommendation for human/manager review — but the feature performs no escalation.
3. **Given** a low-risk routine message, **When** the draft is generated, **Then** the tone is professional and friendly without unnecessary caution.

---

### Edge Cases

- **No upstream classification/risk yet**: generation requires intent + risk + a RAG attempt. If missing, generation returns a clear precondition error (generate them first) — it does not guess.
- **RAG failed / model unavailable**: generation fails gracefully (status not stored as a draft, or stored `failed`-equivalent error response); the message keeps its existing replies; retry allowed.
- **Empty message body**: cannot draft meaningfully → returns a precondition/validation error.
- **Multiple drafts for one message**: a new generation creates a new `SuggestedReply` (history of attempts) rather than overwriting an approved one; the latest draft is shown, prior approved/rejected remain.
- **Editing to empty text**: rejected (an approved reply must have non-empty content).
- **Approve an already-approved reply / reject an approved reply**: invalid transition → rejected.
- **Very long source content**: only the retrieved chunk snippets are used as grounding context (bounded), not entire documents.
- **Conflicting sources**: the draft cites the highest-ranked relevant source(s); it does not assert beyond what sources say.
- **Cross-tenant id guessing**: requesting/modifying another tenant's reply → 404/403; never leaks text or sources.
- **Concurrent edits/approvals**: last write wins for content; once `approved`/`rejected`, content edits are blocked.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST generate a draft reply for a message using its text, intent (Spec 006), risk (Spec 007), and tenant-scoped RAG sources (Spec 009).
- **FR-002**: The system MUST store each draft as a `SuggestedReply` linked to its message, with status `draft_generated`, `generated_text`, `model_name`, `prompt_version`, and timestamps.
- **FR-003**: When the draft uses RAG sources, the system MUST record `source_document_ids` and `source_chunk_ids` and present source references.
- **FR-004**: When a policy/package question has no supporting source (`no_source`/`no_documents`), the draft MUST NOT assert unsupported policy/price/availability; it MUST state the information is not in the uploaded documents and recommend human review (FR-grounding).
- **FR-005**: The AI MUST NOT auto-send any reply. `approved` means human-accepted, not sent.
- **FR-006**: Staff MUST be able to edit a draft; the edit is stored as `edited_text` (preserving `generated_text`) and sets status `edited`.
- **FR-007**: Staff/manager MUST be able to approve a reply, setting status `approved` and recording `approved_by` + `approved_at`.
- **FR-008**: Staff/manager MUST be able to reject a reply, setting status `rejected`.
- **FR-009**: The system MUST reject invalid state transitions (e.g., editing an `approved`/`rejected` reply, approving a `rejected` reply).
- **FR-010**: High-risk messages MUST receive careful wording and MAY include an escalation recommendation, but the feature MUST NOT create escalations or tasks.
- **FR-011**: The system MUST surface the suggested reply (text, status, sources, review controls) on the message detail page (replacing the Spec 005 "Suggested Reply" placeholder).
- **FR-012**: Every suggested reply MUST be tenant-scoped through its message; cross-tenant access MUST be blocked.
- **FR-013**: The draft MUST only reference RAG sources from the message's tenant; cross-tenant sources MUST never be used.
- **FR-014**: The reply MUST be professional, concise, and polite, suitable for wedding/event agency communication.
- **FR-015**: The system MUST support multiple generation attempts per message (each a new `SuggestedReply`) without overwriting an approved one.

### Key Entities

- **Tenant** (Spec 001): scopes everything via the message.
- **User** (Spec 002): the reviewer (`approved_by`); role gates review actions.
- **Message** (Spec 003): the client message being replied to.
- **ClassificationResult** (Spec 006): intent input to generation.
- **RiskAssessment** (Spec 007): risk input controlling tone + escalation note.
- **RagRetrievalResult** (Spec 009): grounding sources; status drives the refuse path.
- **SuggestedReply** (new): the AI draft + review lifecycle for one message.
- **SuggestedReplyStatus** (enum): `draft_generated`, `edited`, `approved`, `rejected`.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client |
| Message | Spec 003 | The client message to reply to |
| Intent | Spec 006 `ClassificationResult` | Drives reply content + framing |
| Risk | Spec 007 `RiskAssessment` | Drives tone + escalation note |
| RAG sources + status | Spec 009 retrieval | Grounding evidence; `no_source`/`no_documents` drive refusal |
| Generate trigger | `POST /messages/{id}/suggested-replies` | Requests a new draft |
| Edit text | `PATCH /suggested-replies/{id}` | Staff-edited reply text |
| Approve / reject | `POST .../approve` / `.../reject` | Human review decisions |

---

## Outputs

| Output | Description |
|--------|-------------|
| Suggested reply draft | `generated_text` + status `draft_generated`, linked to the message |
| Source references | `source_document_ids` + `source_chunk_ids` + displayable source list |
| Edited reply | `edited_text` + status `edited` |
| Approval record | status `approved` + `approved_by` + `approved_at` |
| Rejection | status `rejected` |
| Detail-page panel | Suggested Reply panel (text, sources, status, review controls) |
| Refusal draft | Ungrounded "not in documents — needs human review" text with empty sources |
| 403 / 404 | Cross-tenant / platform-admin / missing message or reply |
| 422 | Invalid edit / invalid transition / precondition not met |

---

## Main Workflow

1. **Upstream signals exist** — the message has an intent (Spec 006), a risk assessment (Spec 007), and a RAG retrieval (Spec 009).
2. **Staff requests a draft** — `POST /messages/{id}/suggested-replies` (or it is generated as part of the message workflow).
3. **AI assembles context** — message text + intent + risk + the tenant's RAG sources (and RAG status).
4. **Grounding decision** — if the question needs policy/package info and RAG is `grounded`, the draft uses + cites those sources; if `no_source`/`no_documents`, the draft refuses to invent and recommends human review.
5. **Tone control** — high-risk messages get careful, empathetic wording and may note escalation is advisable.
6. **Draft stored** — `SuggestedReply` saved with `draft_generated`, text, sources, `model_name`, `prompt_version`, timestamps.
7. **Human review** — staff edits (→ `edited`), approves (→ `approved`, recorded), or rejects (→ `rejected`). Nothing is sent.
8. **Surfaced** — the draft + sources + status + controls appear in the detail page's Suggested Reply panel.

---

## Alternative Workflows

### Grounded Policy Answer (Example 1 & 2)

1. "Can you send me your wedding package prices?" → intent `pricing_request`; RAG returns the package document.
2. The draft summarises the relevant package info **from the source** and cites it.
3. Staff reviews and approves/edits. (Cancellation/deposit example follows the same path with the cancellation/deposit policy and high-risk tone.)

### Unsupported Question — Refuse (Example 3)

1. "Can you organize fireworks with drones and celebrity singers?" → RAG `no_source`.
2. The draft does not invent a policy/price; it says this is not covered in the uploaded documents and the team will confirm / recommends human review.
3. Sources are empty; the reply is flagged ungrounded.

### High-Risk Complaint

1. A high-risk complaint message → careful, empathetic draft acknowledging the concern.
2. The draft may note that manager escalation is advisable.
3. No escalation/task is created; staff handles review (and escalates via the separate feature when it exists).

### Regenerate

1. Staff is unhappy with a draft and requests another.
2. A new `SuggestedReply` is created (prior drafts retained); an already-`approved` reply is never overwritten.

### Cross-Tenant Attempt

1. A Tenant B user requests generation/review for a Tenant A message or reply.
2. Tenant resolution returns 404/403; no Tenant A text or sources are exposed; generation never uses Tenant A sources.

### Generation Failure

1. The generation model (or RAG) is unavailable.
2. The request returns a clear error; no malformed draft is stored; retry allowed.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Generation creates a `SuggestedReply` linked to the message with status `draft_generated`, non-empty text, model_name, prompt_version, timestamps | Integration test: POST → assert fields |
| AC-02 | A grounded policy/package draft records source_document_ids + source_chunk_ids and references them | Integration test: pricing message → assert sources non-empty + referenced |
| AC-03 | An unsupported policy question (`no_source`/`no_documents`) produces a refusal draft with empty sources, no invented facts | Integration test: fireworks message → assert refusal text + empty sources |
| AC-04 | A draft never asserts policy/price/availability not present in cited sources | Integration test/eval: assert no uncited policy facts |
| AC-05 | High-risk message draft uses careful wording and may recommend escalation; no escalation/task created | Integration test: high-risk message → assert tone markers + no escalation/task side effect |
| AC-06 | Editing stores `edited_text`, preserves `generated_text`, sets status `edited` | Integration test: PATCH → assert both fields + status |
| AC-07 | Approve sets status `approved`, records approved_by + approved_at; nothing sent | Integration test: approve → assert fields, assert no send |
| AC-08 | Reject sets status `rejected` | Integration test: reject → assert status |
| AC-09 | Invalid transitions are rejected (edit/approve a terminal reply; approve a rejected one) | Integration test: each → 422 INVALID_STATE_TRANSITION |
| AC-10 | Suggested reply is tenant-scoped; Tenant B cannot read/modify Tenant A reply | Integration test: cross-tenant → 404/403 |
| AC-11 | Draft references only the message tenant's RAG sources | Integration test: assert all source ids belong to the tenant |
| AC-12 | `POST /messages/{id}/suggested-replies` generates; `GET` lists drafts for a message | Integration test: generate then list |
| AC-13 | `GET /suggested-replies/{id}` returns one reply; cross-tenant → 404/403 | Integration test |
| AC-14 | Platform Admin blocked from all suggested-reply endpoints (403) | Integration test: admin → 403 INSUFFICIENT_ROLE |
| AC-15 | The AI never auto-sends; there is no send action/endpoint in this feature | Code/integration test: assert absence |
| AC-16 | Multiple generations create separate replies; an approved reply is never overwritten | Integration test: generate twice + approve → assert history |
| AC-17 | Detail page shows the suggested reply, sources, status, and review controls | Frontend test: assert panel rendering |
| AC-18 | Generation requires upstream intent + risk + RAG; missing → precondition error | Integration test: missing upstream → 409/422 |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenant isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT; `staff`/`manager` review; Platform Admin blocked |
| Spec 003 — Message Simulator | Required | The message being replied to |
| Spec 004 — Message Inbox | Required (light) | Entry point; may show a "reply ready" indicator |
| Spec 005 — Message Detail Page | Required | Surface for the Suggested Reply panel (replaces the placeholder) |
| Spec 006 — Intent Classifier | Required | Intent input |
| Spec 007 — Risk Detection | Required | Risk input (tone + escalation note) |
| Spec 009 — RAG Over Tenant Documents | Required | Grounding sources + `no_source`/`no_documents` refusal signal |
| Generation model (LLM) | Required | Produces the draft text from the assembled, tenant-scoped context |

---

## AI Behavior

- **Inputs to the prompt**: client message text, intent label, risk level + flag, and the tenant's RAG source snippets (with titles/types) plus the RAG status. No raw documents beyond retrieved snippets; no cross-tenant content ever.
- **Grounded generation**: when the message needs policy/package facts and RAG is `grounded`, the model must base those facts on the provided source snippets and cite them. Factual claims about policy/pricing/availability must be traceable to a cited source.
- **Refusal on missing evidence**: when RAG is `no_source`/`no_documents` for a policy/package question, the model must not invent. It states the info is not in the uploaded documents and recommends human review/confirmation. (This is the safety contract inherited from Spec 009's refuse path.)
- **Tone**: professional, concise, polite, suitable for a wedding/event agency. High-risk → careful, empathetic, de-escalating; may suggest manager escalation. Low-risk → friendly and efficient.
- **No autonomous action**: the model only drafts text. It never sends, never creates tasks, never creates escalations. A human must approve.
- **Provenance**: every draft records `model_name` and `prompt_version` so outputs are reproducible/auditable and prompt changes are tracked.
- **Determinism note**: generation may be non-deterministic (LLM); reproducibility is supported via recorded model + prompt version + the exact source ids used, not via identical text.

---

## RAG Grounding Rules

| Rule | Description |
|------|-------------|
| **GR-01: Cite what you use** | Any policy/package fact in the draft must come from a retrieved source and be recorded in `source_document_ids`/`source_chunk_ids`. |
| **GR-02: Refuse without evidence** | If RAG is `no_source`/`no_documents` for a policy/package question, the draft must not assert such facts; it states the info is unavailable and recommends human review. |
| **GR-03: Tenant-only sources** | Only RAG sources from the message's tenant may ground the reply (Spec 009 already guarantees tenant-scoped retrieval). |
| **GR-04: Snippets, not whole docs** | Grounding context is the retrieved chunk snippets (bounded), not entire documents. |
| **GR-05: No source fabrication** | The draft must never cite a source id that was not in the retrieval result. |
| **GR-06: Grounded flag** | The stored reply records whether it is grounded (has sources) or a refusal (no sources), so the UI and downstream can distinguish. |

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` derived from JWT (and the message's tenant). No client-supplied tenant accepted. |
| **SR-02: Reply tenancy** | A `SuggestedReply` is bound to its message's tenant. Tenant A can never read/modify Tenant B replies. |
| **SR-03: Tenant-only grounding** | Generation uses only the message tenant's RAG sources; cross-tenant sources are never included in the prompt (SR/GR-03). |
| **SR-04: Role restriction** | Only `staff` and `manager` may generate/review. Platform Admin → 403. Unauthenticated → 401. |
| **SR-05: Not Found vs Forbidden** | Message/reply not in tenant → 404; in another tenant → 403 (consistent with Specs 005–009). |
| **SR-06: No auto-send** | No code path sends a reply. Approval is human-acceptance only. |
| **SR-07: No autonomous side effects** | Generation/approval create no tasks and no escalations. |
| **SR-08: Provenance integrity** | `approved_by` is the authenticated reviewer; `model_name`/`prompt_version`/source ids cannot be spoofed by the client. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Missing upstream intent/risk/RAG | 409 `PRECONDITION_NOT_MET` (generate them first); no draft stored |
| Generation model unavailable | 503 `MODEL_UNAVAILABLE`; no malformed draft stored; retry allowed |
| RAG unavailable / failed | Generation declines or returns a refusal draft (no invented facts); error surfaced |
| Empty message body | 422 validation; no draft |
| Edit to empty text | 422 `EMPTY_REPLY_TEXT`; no change |
| Edit/approve a terminal (`approved`/`rejected`) reply | 422 `INVALID_STATE_TRANSITION`; no change |
| Approve a `rejected` reply | 422 `INVALID_STATE_TRANSITION` |
| Cross-tenant reply/message access | 404/403 per SR-05; no data exposed |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE` |
| Draft tries to cite a non-retrieved source | Rejected by GR-05 validation; sources limited to the retrieval result |

---

## Edge Cases (summary)

- No upstream signals → precondition error (no guessing).
- RAG/model unavailable → graceful error or refusal; no malformed draft.
- Empty body / empty edit → 422.
- Multiple drafts → new rows; approved never overwritten.
- Terminal-state edits/approvals → 422.
- Long/conflicting sources → bounded snippets; cite top-ranked; no over-assertion.
- Cross-tenant id guessing → 404/403.
- Concurrent edits → last write wins until terminal.

---

## Out of Scope

- **Sending the reply** — no WhatsApp/email/SMS send; nothing is transmitted (`approved` ≠ sent).
- **Task creation** — separate, later feature; generation/approval create no tasks.
- **Escalation workflow** — separate, later feature; drafts may *recommend* escalation but never perform it.
- **Intent classification, risk detection, RAG retrieval** — owned by Specs 006/007/009; consumed here, not re-implemented.
- **Audit logging** — added by the later audit-log feature; reply actions logged there.
- **Multi-turn conversation generation / threading** — single-message reply drafting only for MVP.
- **Auto-approval / auto-regeneration** — every draft requires explicit human action.
- **Tone/style configuration UI** — fixed professional tone for MVP (prompt-driven).
- **Real WhatsApp API, calendar syncing, full CRM** — out of scope entirely.

---

## Assumptions

- Generation requires the message to already have intent (Spec 006), risk (Spec 007), and a RAG retrieval (Spec 009); the API enforces this precondition rather than silently guessing.
- The grounding context is the RAG retrieval's source snippets (Spec 009 `RagRetrievalResult`), already tenant-scoped; this feature does not re-run retrieval logic, it consumes results (and may trigger a retrieval as part of generation).
- A message may have multiple suggested replies over time (regeneration); the latest draft is shown, and approved/rejected history is retained.
- `approved` is a terminal, human-accepted state; sending is a future, separate concern.
- `generated_text` is immutable once stored; edits live in `edited_text`; the effective text is `edited_text` if present else `generated_text`.
- High-risk tone and the escalation recommendation are produced by the prompt using the Spec 007 risk signal; no escalation entity is created here.
- The detail page's "Suggested Reply" placeholder from Spec 005 is replaced by the real panel; remaining placeholders (Create Task, Escalate) stay placeholders.
- `model_name` and `prompt_version` are recorded for every draft for auditability and reproducibility of the generation setup.
