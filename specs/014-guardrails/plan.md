# Implementation Plan: Guardrails

**Branch**: `014-guardrails` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/014-guardrails/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant isolation; tenant-scoped retrieval; cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT; `user_id`/role; manager (read all) + staff (message-scoped)
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): client message text is the scanned input; original body stored as-is
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): surfaces the refusal/hold message + a message's decisions
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/plan.md): retrieved sources for grounding validation; tenant-scoped retrieval
- [Spec 010 — Suggested Replies](../010-suggested-replies/plan.md): the draft checked post-generation; human-approve preserved (never auto-sent)
- [Spec 013 — Audit Logs](../013-audit-logs/plan.md): `AuditService.log_event` (best-effort) for `guardrail_refusal` / `cross_tenant_access_blocked` / `unsupported_answer_refused`

**Note**: This feature does not generate replies, retrieve documents, create tasks, or escalate. It **wraps** the existing 009→010 path with two checks (input/output), persists a `GuardrailDecision` per non-trivial evaluation, and writes a Spec 013 audit log. It is a cross-cutting safety layer.

---

## Summary

Add a guardrail layer with a single service (`GuardrailService`) exposing `check_user_input`, `check_ai_output`, `redact_pii`, and `validate_rag_grounding`. `check_user_input` runs **before** RAG/generation and detects/refuses `prompt_injection`, `system_prompt_disclosure`, and `cross_tenant_access`. `check_ai_output` runs **after** generation and **before** display, validating RAG grounding and detecting `unsupported_answer`, `secret_or_token_exposure`, `system_prompt_disclosure`, and `unsafe_or_unprofessional_reply`, while applying PII redaction to summaries. Each non-trivial evaluation persists a tenant-scoped `GuardrailDecision` (`category`, `action`, `severity`, `reason`, `redacted_text?`, `metadata`, `message_id?`, `suggested_reply_id?`, `created_at`) and writes a Spec 013 audit log (best-effort). Detection is **rule/heuristic-based** (pattern lists + grounding/no-source checks + PII regex) — no trained model or external moderation API in the MVP. The layer **fails safe** (hold output / don't run input on error), **never auto-sends / creates tasks / escalates**, and **never blocks** normal valid messages. A manager dashboard + message-scoped panel read the decisions (tenant-scoped, role-gated, append-only). The reply-generation flow (010) is modified to call the input check before and the output check after, applying the returned action.

---

## Technical Approach

- **Single guardrail service (`GuardrailService`)**: all checks live in one service so the "two chokepoints" (FR-002), redaction (FR-019), and fail-safe (FR-018) behaviors are implemented and tested once. The 009/010 path calls it; there is no path to the model/retriever that skips it.
- **Rule/heuristic detection (MVP)**: `prompt_injection`/`system_prompt_disclosure` use a curated pattern list (override phrases, "system prompt", "hidden rules", role-switch); `cross_tenant_access` matches other-tenant names/ids resolved from the tenant registry; `secret_or_token_exposure` uses token/JWT/key regexes; `unsafe_or_unprofessional_reply` uses a small unsafe/abusive lexicon + an "unauthorized commitment" heuristic; `unsupported_answer` is driven by `validate_rag_grounding` (no-source or claim-without-source). PII uses email/phone regexes. (Decision: rules over a trained classifier for the MVP — see research.)
- **Grounding validation (`validate_rag_grounding`)**: given the draft + the retrieved sources (009), returns `grounded: bool` + `source_document_ids`. No source ⇒ not grounded ⇒ `unsupported_answer`. Heuristic: require at least one supporting source for the answer's factual claims; partial grounding ⇒ `require_human_review` (GR-05).
- **Decision + action model**: each check returns a `GuardrailDecision` (category/action/severity/reason/redacted_text/metadata/refs). The caller applies the action: `allow`/`warn`/`redact` → proceed (with redacted text if any); `require_human_review` → hold the draft; `refuse` → show the professional refusal, not the draft.
- **Fail safe (FR-018, SR-05)**: `check_ai_output` wraps detection in try/except; on error it returns a `human_review_required` `require_human_review` decision (hold, don't show). `check_user_input` on error for a refuse-class signal returns `refuse` (don't invoke the AI). The safe state is never "show/run the unchecked thing".
- **Best-effort audit (FR-012)**: after persisting the decision, call `AuditService.log_event(...)` (Spec 013) — which is itself best-effort and never raises; a failed audit never undoes a `refuse`.
- **Defense-in-depth tenancy (SR-02)**: retrieval is already tenant-scoped (001/009); the `cross_tenant_access` check is an additional explicit refusal + audit, not the sole boundary. Decisions store **no** target-tenant data.
- **Redaction everywhere (FR-019, SR-08)**: a shared `redact_text` (PII + secret/JWT/key + prompt markers) runs over every `reason`/`redacted_text`/`metadata`/summary before persistence; the Spec 013 redactor is the backstop.
- **Append-only decisions**: like Spec 013 audit logs, `guardrail_decisions` has no update/delete path; reads are role-gated and tenant-scoped (404/403).

---

## Backend Tasks

1. **`schemas/guardrails.py`** — Pydantic: `GuardrailDecisionResponse`, `GuardrailDecisionListItem`, `GuardrailDecisionListResponse`, `GuardrailDecisionFilters`, `CheckInputRequest`, `CheckOutputRequest`, `CheckResult`; plus `GuardrailCategory`, `GuardrailAction`, `GuardrailSeverity` enums.
2. **`services/guardrail_service.py`**:
   - `check_user_input(session, *, tenant_id, user_id, role, message_id=None, text) -> CheckResult` — pre-RAG/generation; detects prompt_injection / system_prompt_disclosure / cross_tenant_access; persists decision + audit; fail-safe to `refuse` on probe-class error.
   - `check_ai_output(session, *, tenant_id, user_id, message_id, suggested_reply_id, draft_text, sources) -> CheckResult` — post-generation; validate grounding, scan unsupported/secret/prompt/unsafe; apply PII redaction to summary; persist decision + audit; fail-safe to `require_human_review` on error.
   - `redact_pii(text) -> (redacted_text, found: bool)` — email/phone → placeholders.
   - `validate_rag_grounding(draft_text, sources) -> GroundingResult` — `grounded`, `source_document_ids`, `partial`.
   - `list_guardrail_decisions(session, tenant_id, filters, *, limit, offset)` — tenant-scoped, filtered, newest-first, paginated.
   - `get_guardrail_decision(session, tenant_id, decision_id)` — tenant-resolve (404/403); full redacted decision.
   - `decisions_for_message(session, tenant_id, message_id, *, staff_view=False)` — message-scoped (tenant-resolve message).
3. **`services/guardrail_rules.py`** — pattern/lexicon/regex sources: `INJECTION_PATTERNS`, `DISCLOSURE_PATTERNS`, `SECRET_PATTERNS`, `UNSAFE_LEXICON`, `COMMITMENT_MARKERS`, `EMAIL_RE`, `PHONE_RE`; plus `detect_injection(text)`, `detect_disclosure(text)`, `detect_cross_tenant(text, tenant_registry)`, `detect_secret(text)`, `detect_unsafe(text)`. Unit-tested in isolation.
4. **`services/guardrail_redaction.py`** — `redact_text(text) -> (clean, flags)` combining PII + secret/JWT/key + prompt-marker stripping; used on every decision field + summary (FR-019). (May reuse Spec 013 `audit_redaction` as the audit-side backstop.)
5. **Integration into the reply path (010 / `reply_service.py`)**:
   - Call `check_user_input` **before** RAG/generation; if `refuse`, short-circuit (no RAG, no model) and return the refusal payload.
   - After generation, call `check_ai_output` **before** returning the draft; apply the action (`allow`/`redact` → return [redacted] draft; `require_human_review` → return held draft + flag; `refuse` → return professional refusal, not the draft).
6. **Audit wiring (013)** — map decisions to audit events: `prompt_injection`/`system_prompt_disclosure`/`unsafe_*`/`secret_*` → `guardrail_refusal`; `cross_tenant_access` → `cross_tenant_access_blocked` (via `log_cross_tenant_blocked`); `unsupported_answer` → `unsupported_answer_refused`. Best-effort.
7. **`api/v1/guardrails.py`** — optional `POST /check-input` + `POST /check-output` (testing/demo, same logic) and the read endpoints (`GET /api/guardrail-decisions`, `/{id}`, `GET /api/messages/{id}/guardrail-decisions`) with `require_role`.
8. **Config** — `GUARDRAILS_ENABLED`, `GUARDRAIL_LOG_ALLOW_DECISIONS` (persist trivial allows or not), `GUARDRAIL_MAX_SCAN_CHARS`, `GUARDRAIL_DECISIONS_MAX_LIMIT`, `GUARDRAIL_STAFF_MESSAGE_VIEW_ENABLED` in settings.
9. **Router mount** — register the guardrails router at `/api` in `main.py`.

---

## Guardrail Service Tasks

1. **`check_user_input` contract** — keyword-only; returns a `CheckResult` (decision + whether to proceed). For a clean message → `allow` (optionally not persisted per `GUARDRAIL_LOG_ALLOW_DECISIONS`). For a probe → `refuse` (security), persist + audit, `proceed=False`.
2. **`check_ai_output` contract** — keyword-only; runs grounding → unsupported/secret/prompt/unsafe scans → PII redaction of summary; returns the action + the (possibly redacted) text to show or a refusal/hold flag.
3. **Detection pipeline** — order: input = injection → disclosure → cross_tenant (most-severe-wins, all `security`); output = grounding/unsupported → secret/prompt → unsafe → pii_redact (a `refuse` short-circuits display; redaction always applied to summaries).
4. **Fail-safe wrapper** — try/except around both checks: output error → `require_human_review`; input probe-path error → `refuse`. Never return "show/run unchecked".
5. **Decision builder** — one helper assembles a `GuardrailDecision` (category/action/severity/reason/redacted_text/metadata/refs), runs `redact_text` over every field, persists it, then writes the Spec 013 audit log (best-effort).
6. **No side effects guarantee** — the service has no dependency on task/escalation/reply-send code paths; a static check + a test asserts the guardrail path never calls them (FR-015, SR-06, AC-18).

---

## Pre-Processing Checks (`check_user_input`)

1. **prompt_injection** — match override/role-switch patterns ("ignore (all )?previous instructions", "you are now", "disregard the above", "system:", "developer:") → `refuse`, severity `security`, audit `guardrail_refusal`. Do **not** execute or partially comply.
2. **system_prompt_disclosure** — match "show/reveal/print your (system )?prompt/hidden rules/instructions/policies" → `refuse`, `security`. Never echo any prompt/policy text.
3. **cross_tenant_access** — resolve other-tenant names/slugs/ids from the tenant registry; if the input references a tenant ≠ caller's → `refuse`, `security`, audit `cross_tenant_access_blocked` in the caller's tenant (no target data).
4. **benign-topic guard (FR-014/AC-20)** — topical words ("refund", "policy", "cancel") alone never trigger; only override/disclosure/cross-tenant **intent** does.
5. **empty/oversized** — empty/whitespace → `allow`; oversized → cap scan to `GUARDRAIL_MAX_SCAN_CHARS`, optionally `human_review_required`.

---

## Post-Generation Checks (`check_ai_output`)

1. **grounding/unsupported** — call `validate_rag_grounding`; no source or ungrounded claim → `unsupported_answer` `refuse`/`require_human_review`; audit `unsupported_answer_refused`.
2. **secret_or_token_exposure** — scan draft for JWT/API-key/secret patterns → `refuse`/`redact`; secret never shown.
3. **system_prompt_disclosure (output side)** — scan for leaked system-prompt text → `refuse`.
4. **unsafe_or_unprofessional_reply** — unsafe lexicon / unauthorized-commitment markers → `require_human_review`/`refuse`.
5. **pii_redaction** — `redact_pii` on any produced summary/`redacted_text` (does not block; `redact`/`info`).
6. **apply action** — `refuse` → professional refusal (not the draft); `require_human_review` → hold; `redact` → redacted draft; `allow` → draft (still 010 human-approve, never auto-sent).

---

## RAG Grounding Validation Tasks

1. **`validate_rag_grounding(draft_text, sources)`** — return `grounded: bool`, `source_document_ids: list`, `partial: bool`. No sources ⇒ `grounded=False`.
2. **Claim coverage heuristic (MVP)** — treat the answer as grounded if its factual assertions are covered by at least one retrieved chunk (lexical/semantic overlap threshold from research); a clearly novel claim (price/policy/availability not in any chunk) flips `partial=True`.
3. **No-source path** — wire to the 009 `rag_no_source_found` signal: if RAG already reported no source, skip generation and go straight to the `unsupported_answer` refusal.
4. **Metadata (ids only)** — record `source_document_ids` + `grounded`/`partial` in decision metadata; never the document text (GR-06).
5. **Tenant-scope assertion** — sources passed in are already the caller tenant's (009); grounding never considers another tenant's document (GR-03).

---

## PII Redaction Tasks

1. **`redact_pii(text)`** — `EMAIL_RE` → `[EMAIL_REDACTED]`, `PHONE_RE` → `[PHONE_REDACTED]`; return `(redacted, found)`.
2. **Apply to summaries/decisions, not the stored message** — the 003 message body is untouched; only guardrail summaries/`redacted_text` and Spec 013 audit summaries use placeholders (PR-01, AC-10).
3. **Stable placeholders** — consistent tokens for readability (PR-04).
4. **Non-blocking** — PII → action `redact`, severity `info`; never `refuse` for PII alone (PR-03, FR-008).
5. **Phone-format coverage** — international (`+961…`) and common local formats; unit-tested against the Example-4 string.

---

## Audit-Log Integration Tasks

1. **Decision → audit mapping** — `guardrail_refusal` (injection/disclosure/secret/unsafe), `cross_tenant_access_blocked` (cross_tenant), `unsupported_answer_refused` (unsupported). (Spec 013 already defines these event types.)
2. **Best-effort call** — after persisting the decision, call `AuditService.log_event` / `log_cross_tenant_blocked`; never let an audit failure undo or raise into the guardrail (FR-012, AC-12).
3. **Redacted summary** — pass a redacted summary (PII/secret/prompt-free) so the Spec 013 entry is safe; the 013 redactor is the backstop (PR-06).
4. **No refused/offending text** — audit metadata carries category/action/`source_document_ids`/`attempted_route` only — never the system prompt, the refused answer, the secret, or cross-tenant data.

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/guardrails/check-input` | POST | staff/manager (or service) | Run input check on text (testing/demo + programmatic use) |
| `/api/guardrails/check-output` | POST | staff/manager (or service) | Run output check on a draft + sources |
| `/api/guardrail-decisions` | GET | manager | Tenant-wide decisions list with filters + pagination |
| `/api/guardrail-decisions/{decision_id}` | GET | manager | Get one decision (full redacted) |
| `/api/messages/{message_id}/guardrail-decisions` | GET | staff (their message), manager | Message-scoped decisions |

- All resolve tenant first (404/403); `tenant_id`/`user_id`/`role` from JWT only.
- Filters validated (422 on bad enum/date/pagination); list bounded by `GUARDRAIL_DECISIONS_MAX_LIMIT`, newest-first.
- No update/delete routes (append-only); any such method → 405.
- `check-input`/`check-output` run the **same** service logic as the in-process path; they are conveniences, not a second code path.

---

## Frontend Integration Tasks

1. **`api/guardrails.ts`** — typed client: `checkInput(text)`, `checkOutput(payload)`, `listGuardrailDecisions(filters, page)`, `getGuardrailDecision(id)`, `decisionsForMessage(messageId)`.
2. **`types/guardrails.ts`** — `GuardrailCategory`, `GuardrailAction`, `GuardrailSeverity`, `GuardrailDecision` TS types.
3. **Reply UI integration (Spec 010 / Message Detail 005)** — when a draft is `refuse`d, show a **professional refusal banner** (e.g., "This can't be answered from your business documents — please confirm with the client.") instead of the draft; when `require_human_review`, show the held draft with a "needs review" badge; when `redact`, show the redacted draft. Never render the offending output.
4. **`pages/GuardrailDecisionsPage.tsx`** — `/guardrail-decisions` manager dashboard: newest-first table (time, category, action, severity, message, reason) + filter bar (category, action, severity, date range, message) + pagination.
5. **`components/guardrails/GuardrailDecisionTable.tsx` + `Row.tsx`** — category chip, action badge, severity badge (info/low/medium/high/security), message link, relative time.
6. **`components/guardrails/GuardrailDecisionDetail.tsx`** — single decision drawer: category/action/severity/reason/redacted_text/metadata/refs; read-only (no edit/delete).
7. **`components/guardrails/GuardrailRefusalBanner.tsx`** — the staff-facing professional refusal/hold message used in the reply flow.
8. **Message detail panel (005)** — a "Guardrails" panel showing `decisionsForMessage` (staff-visible) so staff understand a refusal/hold.
9. **States** — loading, empty, 422 inline, 403 (cross-tenant/role), 404; **no** edit/delete affordances; never any control to "show the blocked content".

---

## Testing Tasks

**Backend unit** — `tests/unit/test_guardrail_rules.py`: injection/disclosure/cross-tenant/secret/unsafe detection precision incl. benign-topic negatives (AC-20); `tests/unit/test_guardrail_redaction.py`: PII placeholders (Example-4 string), secret/JWT/key stripping, no forbidden content (AC-09, AC-17); `tests/unit/test_grounding.py`: no-source ⇒ not grounded, paraphrase ⇒ grounded, partial ⇒ review (GR-01..05); `tests/unit/test_guardrail_service.py`: fail-safe (injected error → hold/refuse, AC-19), no side effects (AC-18).

**Backend integration** — `tests/integration/test_guardrails.py`:
- Normal message → allow + draft (AC-01); injection refuse + no disclosure (AC-02); disclosure refuse (AC-03)
- Cross-tenant request → refuse + no B source + audit in A (AC-04)
- No-source/ungrounded → unsupported refuse + audit (AC-05); output-after-generation ordering (AC-06)
- Secret in draft → refuse/redact (AC-07); unsafe draft → review/refuse (AC-08)
- PII → placeholders in summary/audit + not blocked + stored body intact (AC-09, AC-10)
- Decision persisted with fields (AC-11); audit written best-effort incl. injected audit failure (AC-12)
- Manager list filters + tenant scope (AC-13); get one + cross-tenant 404/403 (AC-14); message-scoped + staff (AC-15)
- Tenant isolation (AC-16); redaction over representative decisions (AC-17); no auto-send/task/escalation (AC-18)
- Fail-safe hold/no-invoke (AC-19); benign topical messages allow (AC-20); 422/401/403/404 (AC-22)

**Frontend** — refusal/hold/redact banner rendering (AC-21); decisions dashboard + filters; decision detail redacted; message panel; no edit/delete or "reveal" controls.

---

## Build Order

1. **Schemas + enums** — `GuardrailCategory`/`Action`/`Severity` + DTOs + filter model.
2. **DB + model** — Alembic migration + `GuardrailDecision` model + indexes (append-only).
3. **Rules + redaction + grounding** — `guardrail_rules.py`, `guardrail_redaction.py`, `validate_rag_grounding` with unit tests (detection precision, PII, grounding).
4. **Service** — `check_user_input` / `check_ai_output` (decision builder + fail-safe + best-effort audit) + read functions; assert no side effects.
5. **Reply-path wiring (010)** — input check before RAG/generation, output check before display, apply action; audit mapping to 013.
6. **API** — read endpoints + optional check-input/check-output + router mount + role/error mapping; integration tests (AC-01..AC-22).
7. **Frontend** — types + API client → refusal/hold/redact banner in the reply flow → decisions dashboard + filters → decision detail → message panel → states (no edit/delete/reveal).
8. **Validation** — run the 7-step quickstart (normal pass, injection, disclosure, cross-tenant, unsupported, PII summary, invented-policy hold) and confirm all 22 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/014-guardrails/
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
│   │   └── guardrails.py                 # check-input/check-output (optional) + read endpoints
│   ├── services/
│   │   ├── guardrail_service.py          # check_user_input / check_ai_output / reads (fail-safe, best-effort audit)
│   │   ├── guardrail_rules.py            # injection/disclosure/cross-tenant/secret/unsafe detection
│   │   ├── guardrail_redaction.py        # redact_pii + secret/prompt redaction
│   │   └── guardrail_grounding.py        # validate_rag_grounding
│   ├── models/
│   │   └── guardrail_decision.py         # GuardrailDecision ORM model (append-only)
│   └── schemas/
│       └── guardrails.py                 # Pydantic + Guardrail{Category,Action,Severity} enums
├── alembic/versions/
│   └── 00xx_create_guardrail_decisions.py
└── tests/
    ├── integration/
    │   └── test_guardrails.py
    └── unit/
        ├── test_guardrail_rules.py
        ├── test_guardrail_redaction.py
        ├── test_grounding.py
        └── test_guardrail_service.py

frontend/
└── src/
    ├── api/
    │   └── guardrails.ts
    ├── types/
    │   └── guardrails.ts
    ├── pages/
    │   └── GuardrailDecisionsPage.tsx
    └── components/guardrails/
        ├── GuardrailDecisionTable.tsx
        ├── GuardrailDecisionRow.tsx
        ├── GuardrailDecisionDetail.tsx
        ├── GuardrailDecisionFilters.tsx
        └── GuardrailRefusalBanner.tsx
```

Modified files:

```
backend/app/main.py                                  # mount guardrails router
backend/app/core/config.py                           # GUARDRAIL_* settings
backend/app/services/reply_service.py (010)          # call check_user_input (before) + check_ai_output (after); apply action
backend/app/services/rag_service.py (009)            # pass retrieved sources to grounding; no-source → unsupported path
backend/app/services/audit_service.py (013)          # reuse log_event / log_cross_tenant_blocked (no change, just called)
frontend/src/App.tsx                                 # add /guardrail-decisions route (manager)
frontend/src/pages/ConversationDetailPage (005)      # refusal/hold banner + Guardrails panel
frontend/src/components/NavBar (or Sidebar)          # add Guardrails nav item (manager)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–013. Guardrails are a cross-cutting safety layer implemented as a single `GuardrailService` with two chokepoints (input/output) called by the 009→010 path, a rule/heuristic detection layer, a grounding validator, a shared redactor, an append-only `GuardrailDecision` record, and a tenant-scoped role-gated read surface. The "fail-safe", "no autonomous side effects", "redaction in every field", and "never blocks valid messages" guarantees live in the service so call sites stay thin and cannot bypass them.
