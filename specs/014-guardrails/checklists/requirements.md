# Requirements Checklist: Guardrails

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-08
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (safety, trust, transparency) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI safety, RAG grounding, Privacy/redaction, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Guardrail service provides `check_user_input` (pre) and `check_ai_output` (post), each returning a `GuardrailDecision` (FR-001)
- [ ] Input check runs **before** RAG/generation; output check runs **after** generation, **before** display (FR-002, AC-06)
- [ ] `prompt_injection` detected and `refuse`d; injected instruction never executed / no partial compliance (FR-003, AC-02)
- [ ] `system_prompt_disclosure` `refuse`d; system prompt/hidden instructions/policies/keys/secrets/JWTs never returned (FR-004, AC-03)
- [ ] `cross_tenant_access` detected (name or id) and `refuse`d; no other-tenant data retrieved/exposed (FR-005, AC-04)
- [ ] RAG grounding validated; `unsupported_answer` `refuse`/`require_human_review` incl. no-source case (FR-006, AC-05)
- [ ] Replies never invent policies/prices/refunds/availability/commitments absent from documents (FR-007, AC-05)
- [ ] `redact_pii` → `[EMAIL_REDACTED]`/`[PHONE_REDACTED]` in summaries/audit; PII alone never blocks (FR-008, AC-09)
- [ ] `secret_or_token_exposure` in output `refuse`/`redact`; secret never shown (FR-009, AC-07)
- [ ] `unsafe_or_unprofessional_reply` → `require_human_review`/`refuse`; never auto-ready (FR-010, AC-08)
- [ ] Each non-trivial evaluation persists a tenant-scoped `GuardrailDecision` with all fields + refs (FR-011, AC-11)
- [ ] Each decision writes a Spec 013 audit log, best-effort (FR-012, AC-12)
- [ ] Refusals/holds surface to staff as a clear professional message; no offending output/prompt/secret/cross-tenant data shown (FR-013, AC-21)
- [ ] Normal valid wedding/event messages are NOT blocked → `allow` (FR-014, AC-01, AC-20)
- [ ] Guardrails never auto-send, never create tasks, never escalate; may set `require_human_review` (FR-015, AC-18)
- [ ] Managers list/get decisions (filters + pagination); staff read message-scoped (FR-016, AC-13, AC-15)
- [ ] Every read tenant-scoped; cross-tenant blocked; client-supplied tenant ignored (FR-017, AC-16)
- [ ] Fail safe: output error → hold; input probe error → don't invoke AI (FR-018, AC-19)
- [ ] `redacted_text`/`reason`/`metadata` themselves redacted — no prompt/secret/JWT/key/raw-PII/cross-tenant data (FR-019, AC-17)
- [ ] Input checks run on client message text (003) and staff free-text queries via the same path (FR-020)

---

## AI Safety Requirements

- [ ] Two chokepoints: no path to the model/retriever skips input check; no path to staff skips output check (FR-002, AC-06)
- [ ] Client/staff text treated as data, never instructions; injection refused, not obeyed (FR-003, AC-02)
- [ ] No disclosure of system prompt/hidden rules/internal policy/secrets/keys/JWTs in any output/decision/summary (FR-004, AC-03, AC-17)
- [ ] Grounded-only answers; unsupported claims refused or held (FR-006, FR-007, AC-05)
- [ ] Fail safe, not open: error → hold output / don't run refuse-class input (FR-018, AC-19)
- [ ] Advisory, never autonomous: no auto-send/task/escalation; human acts on a hold (FR-015, AC-18)
- [ ] Borderline → `require_human_review` (held), not silently dropped

---

## RAG Grounding Requirements

- [ ] Source-backed claims only; unsupported claims → `unsupported_answer` (GR-01, AC-05)
- [ ] No-source ⇒ refuse with safe "not in your documents" message (GR-02, AC-05)
- [ ] Grounding validated only against the caller tenant's retrieved documents (GR-03)
- [ ] Faithful paraphrase passes; invention fails (GR-04)
- [ ] Partial grounding ⇒ at least `require_human_review` (GR-05)
- [ ] Grounding metadata stores `source_document_ids`/`grounded` (ids only), never document text (GR-06)
- [ ] `validate_rag_grounding` returns `grounded` / `source_document_ids` / `partial`

---

## PII Redaction Requirements

- [ ] Emails → `[EMAIL_REDACTED]`, phones → `[PHONE_REDACTED]` in summaries/`redacted_text`/audit (FR-008, PR-01, AC-09)
- [ ] Original stored message body (003) is unchanged by redaction (PR-01, AC-10)
- [ ] PII detection → `redact` (severity `info`), never `refuse` (PR-03, FR-008)
- [ ] Stable placeholders for readability (PR-04)
- [ ] Example-4 string redacts to "Client provided contact details [EMAIL_REDACTED], [PHONE_REDACTED]." (AC-09)
- [ ] International (`+961…`) and local phone formats covered

---

## Security Requirements

- [ ] `tenant_id`/`user_id`/`role` from JWT only; client-supplied tenant ignored (SR-01)
- [ ] Tenant-scoped retrieval is the hard boundary; guardrail is defense-in-depth (SR-02)
- [ ] `cross_tenant_access_blocked` logged in attempting tenant only, no target data (SR-03, AC-04)
- [ ] No disclosure of internals; output checks backstop input checks (SR-04, AC-03, AC-07)
- [ ] Fail safe on guardrail error (SR-05, AC-19)
- [ ] No autonomous side effects (auto-send/task/escalation) (SR-06, AC-18)
- [ ] Role-gated, tenant-scoped reads; Platform Admin/unauth blocked (SR-07, AC-16, AC-22)
- [ ] Redaction in every stored field + audit summary (SR-08, FR-019, AC-17)

---

## Tenant Isolation Requirements

- [ ] List/get returns only the caller's tenant decisions (AC-13, AC-16)
- [ ] Tenant A cannot read a Tenant B decision (404/403) (AC-14, AC-16)
- [ ] Tenant A cannot query Tenant B's message-scoped decisions (AC-15, AC-16)
- [ ] `cross_tenant_access` decision/audit stores no target-tenant data (SR-03, AC-04)
- [ ] No other-tenant document is ever retrieved for grounding (GR-03, AC-04)
- [ ] A client-supplied `tenant_id` is ignored (SR-01)
- [ ] The decision/audit surface never becomes a cross-tenant leak vector (AC-17)

---

## Audit-Log Integration Requirements

- [ ] `prompt_injection`/`system_prompt_disclosure`/`secret_*`/`unsafe_*` → `guardrail_refusal` (FR-012, AC-12)
- [ ] `cross_tenant_access` → `cross_tenant_access_blocked` in caller's tenant (FR-012, AC-04)
- [ ] `unsupported_answer` → `unsupported_answer_refused` (FR-012, AC-05)
- [ ] Audit is best-effort: failure never breaks the guardrail decision (FR-012, AC-12)
- [ ] Audit summary is redacted (PII/secret/prompt-free); Spec 013 redactor is the backstop (PR-06)
- [ ] Audit metadata carries category/action/`source_document_ids`/`attempted_route` only — never refused text/secret/prompt/cross-tenant data

---

## API / Service Requirements

- [ ] `POST /api/guardrails/check-input` runs the input check; `refuse` is a normal 200 (FR-001, AC-02)
- [ ] `POST /api/guardrails/check-output` runs the output check; `refuse`/`require_human_review` is a normal 200 (FR-001, AC-05)
- [ ] `GET /api/messages/{id}/guardrail-decisions` manager + staff (their message); cross-tenant → 404/403 (FR-016, AC-15)
- [ ] `GET /api/guardrail-decisions` manager-only; filters + pagination; newest-first (FR-016, AC-13)
- [ ] `GET /api/guardrail-decisions/{id}` manager-only; full redacted decision; cross-tenant → 404/403 (FR-016, AC-14)
- [ ] Internal functions `check_user_input` / `check_ai_output` / `redact_pii` / `validate_rag_grounding` are the primary mechanism
- [ ] No create/update/delete routes for decisions; mutate attempts → 405 (append-only)
- [ ] Role matrix enforced; Platform Admin 403; unauthenticated 401 (AC-22)
- [ ] Error responses use consistent `error_code` values per the contract
- [ ] List bounded by `GUARDRAIL_DECISIONS_MAX_LIMIT`; invalid filter/pagination/payload → 422 (AC-22)

---

## Data Requirements

- [ ] `guardrail_decisions` table created via Alembic migration (no `updated_at`)
- [ ] `tenant_id` FK + index; `message_id` nullable FK (`ON DELETE SET NULL`); `suggested_reply_id` nullable FK (`ON DELETE SET NULL`)
- [ ] `category`/`action`/`severity` NOT NULL; `reason`/`redacted_text` TEXT nullable; `metadata` JSONB default `{}`
- [ ] `GuardrailCategory` enum (prompt_injection, system_prompt_disclosure, cross_tenant_access, unsupported_answer, pii_redaction, unsafe_or_unprofessional_reply, secret_or_token_exposure, human_review_required)
- [ ] `GuardrailAction` enum (allow, warn, redact, refuse, require_human_review)
- [ ] `GuardrailSeverity` enum (info, low, medium, high, security)
- [ ] Indexes on `(tenant_id, created_at desc)`, `(tenant_id, category)`, `(tenant_id, action)`, `(tenant_id, severity)`, `(tenant_id, message_id)`
- [ ] `created_at` server-assigned; ordering deterministic (created_at desc, id tiebreak)
- [ ] Append-only enforced at the data/service layer (no mutation path; DB revocation recommended)
- [ ] No raw PII / prompt / secret / cross-tenant data persisted in any column (FR-019, AC-17)

---

## Testing Requirements

- [ ] Unit: rules — injection/disclosure/cross-tenant/secret/unsafe detection incl. benign-topic negatives (AC-02, AC-03, AC-04, AC-20)
- [ ] Unit: redaction — PII placeholders (Example-4), secret/JWT/key stripping, no forbidden content (AC-09, AC-17)
- [ ] Unit: grounding — no-source ⇒ not grounded, paraphrase ⇒ grounded, partial ⇒ review (GR-01..05, AC-05)
- [ ] Unit: service — fail-safe (injected error → hold/refuse), no side effects (AC-18, AC-19)
- [ ] Integration: normal message allow + draft (AC-01); injection refuse + no disclosure (AC-02); disclosure refuse (AC-03)
- [ ] Integration: cross-tenant refuse + no B source + audit in A (AC-04)
- [ ] Integration: ungrounded/no-source unsupported refuse + audit (AC-05); output-after-generation ordering (AC-06)
- [ ] Integration: secret in draft refuse/redact (AC-07); unsafe draft review/refuse (AC-08)
- [ ] Integration: PII placeholders in summary/audit + not blocked + stored body intact (AC-09, AC-10)
- [ ] Integration: decision persisted with fields (AC-11); audit best-effort incl. injected failure (AC-12)
- [ ] Integration: manager list filters + tenant scope (AC-13); get one + cross-tenant 404/403 (AC-14); message-scoped + staff (AC-15)
- [ ] Integration: tenant isolation (AC-16); redaction over representative decisions (AC-17); no auto-send/task/escalation (AC-18)
- [ ] Integration: fail-safe hold/no-invoke (AC-19); benign topical messages allow (AC-20); 422/401/403/404 (AC-22)
- [ ] Frontend: refusal/hold/redact banner (AC-21); decisions dashboard + filters; detail redacted; message panel; no edit/delete/reveal controls
- [ ] Quickstart: all 7 steps (normal pass, injection, disclosure, cross-tenant, unsupported, PII summary, invented-policy hold)

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No auto-sending of replies (Spec 010 human-approve preserved)
- [ ] No creating tasks (011) inside this feature
- [ ] No creating escalations (012) inside this feature
- [ ] No real WhatsApp API / outbound messaging
- [ ] No calendar syncing / full CRM
- [ ] No per-message guardrail disable/override toggle in the UI
- [ ] No trained ML safety classifier / external moderation API (rules/heuristics in MVP)
- [ ] No editing or deleting guardrail decisions (append-only)
- [ ] No exposing system prompts, secrets, tokens, API keys, or hidden instructions
- [ ] No cross-tenant retrieval or cross-tenant metadata leakage
- [ ] No unsupported AI answers presented as ready replies
- [ ] No retention / export / SIEM / alerting for decisions (same deferral as Spec 013)

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order): build rules + redaction + grounding (unit-tested) → the service (two chokepoints, fail-safe, best-effort audit) → wire into the 010 reply path → read API → frontend.
- Hard guarantees to verify: (1) **two chokepoints** — input check before RAG/generation, output check before display, no bypass; (2) **fail safe** — a checker error holds output / does not run a refuse-class input, never fail open; (3) **redaction** — no prompt/secret/JWT/key/raw-PII/cross-tenant data in any decision field or audit summary; (4) **tenant isolation** — no other-tenant retrieval, decisions store no target-tenant data, `cross_tenant_access_blocked` written in the attacker's tenant only; (5) **no autonomous side effects** — never auto-send/task/escalate; (6) **never blocks valid messages** — routine wedding/event questions pass.
- This feature **wraps** the 009→010 path and writes Spec 013 audit logs; it does not generate replies, retrieve documents, create tasks, or escalate.
