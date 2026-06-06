# Implementation Plan: Suggested Replies

**Branch**: `010-suggested-replies` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-suggested-replies/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT; `staff`/`manager` review; Platform Admin blocked
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): messages
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): Suggested Reply panel (replaces the placeholder)
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): intent input
- [Spec 007 — Risk Detection](../007-risk-detection/plan.md): risk input (tone + escalation note)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/plan.md): grounding sources + `no_source`/`no_documents` refusal signal

**Downstream**: task-creation and escalation features will consume approved replies / risk later. Not built here.

---

## Summary

Add an AI draft-reply step that consumes four upstream signals — message text, intent (006), risk (007), and tenant-scoped RAG sources (009) — and produces a professional draft for human review. A new `suggested_replies` table stores `generated_text`, `edited_text`, `status`, `source_document_ids`, `source_chunk_ids`, `model_name`, `prompt_version`, review metadata, and timestamps, all scoped via the message's tenant. A `SuggestedReplyService` assembles a tenant-only prompt context, calls a `ReplyGenerator` (LLM behind an interface), enforces the **grounding/refusal** rules (no source → no invented facts), applies **risk-based tone**, and persists the draft. Six REST endpoints cover generate / list / get / edit / approve / reject — with a strict status state machine and **no send path**. The draft + sources + review controls replace the Spec 005 "Suggested Reply" placeholder. The feature creates no tasks and no escalations and never auto-sends.

---

## Technical Approach

- **Precondition gate**: generation requires the message to have intent (006), risk (007), and a RAG retrieval (009). The service fetches these; if any is missing → 409 `PRECONDITION_NOT_MET` (no guessing).
- **Context assembly (tenant-only)**: build a prompt from message text + intent + risk + the RAG source snippets (titles/types/snippets) for the message's tenant. Cross-tenant content can never enter the prompt (sources come from Spec 009's tenant-scoped results).
- **Grounding/refusal in the service, not just the prompt**: if RAG status is `no_source`/`no_documents` for a policy/package question, the service routes to a refusal template (no invented facts, recommend human review) and stores empty sources + `grounded=false`. Cited source ids are validated against the actual retrieval result (GR-05).
- **Risk-based tone**: the prompt is parameterised by risk level/flag; high-risk → careful/empathetic + optional escalation note (no escalation created).
- **Generator behind an interface**: `ReplyGenerator.generate(context) -> text` with `model_name` + `prompt_version`; an LLM in prod, a deterministic stub in tests. Failure → 503, no malformed draft stored.
- **Status state machine**: `draft_generated → edited → approved | rejected`; terminal states immutable for content; invalid transitions → 422.
- **No send, no side effects**: there is no endpoint, service method, or queue that sends a reply, creates a task, or creates an escalation (SR-06, SR-07).

---

## Backend Tasks

1. **`schemas/suggested_reply.py`** — Pydantic: `GenerateRequest` (optional regen flag), `SuggestedReplyResponse`, `EditRequest`, `ApproveResponse`, `RejectResponse`, `SuggestedReplyListResponse`, plus `SuggestedReplyStatus` enum and an embedded `ReplySource` (doc id/title/type, chunk id, snippet).
2. **`ai/reply_generator.py`** — `ReplyGenerator` interface + LLM impl + deterministic test stub; exposes `model_name`, `prompt_version`; raises `GenerationUnavailable`.
3. **`ai/reply_prompt.py`** — versioned prompt builder: assembles message/intent/risk/source-snippet context; separate grounded vs refusal templates; tone variation by risk; `PROMPT_VERSION` constant.
4. **`services/suggested_reply_service.py`**:
   - `generate(session, tenant_id, user, message_id, force=False)` — precondition checks (intent/risk/RAG), assemble context, branch grounded vs refusal, call generator, validate cited sources ⊆ retrieval, persist `draft_generated`.
   - `list_for_message(session, tenant_id, message_id)` — tenant-resolve message, return replies (newest first).
   - `get(session, tenant_id, reply_id)` — tenant-resolve reply.
   - `edit(session, tenant_id, reply_id, text)` — non-terminal only; store `edited_text`, status `edited`.
   - `approve(session, tenant_id, user, reply_id)` — non-terminal → `approved`, record `approved_by`/`approved_at`; no send.
   - `reject(session, tenant_id, reply_id)` — non-terminal → `rejected`.
5. **`api/v1/suggested_replies.py`** — six endpoints with `require_role(staff, manager)` + error→HTTP + state-machine guards.
6. **Reuse upstream services** — read `ClassificationResult` (006), `RiskAssessment` (007), and call/read RAG (009) for sources; do not duplicate their logic.
7. **Config** — `REPLY_MODEL_NAME`, `REPLY_PROMPT_VERSION`, `REPLY_MAX_CHARS`, `REPLY_SOURCE_SNIPPET_LIMIT` in settings.
8. **Router mount** — register the router at `/api` in `main.py`.

---

## Database Tasks

1. **Alembic migration** — create `suggested_replies`:
   - `id` UUID PK
   - `tenant_id` UUID NOT NULL FK → tenants, indexed (denormalised from message)
   - `message_id` UUID NOT NULL FK → messages, `ON DELETE CASCADE`, indexed
   - `generated_text` TEXT NOT NULL (immutable original)
   - `edited_text` TEXT NULL
   - `status` VARCHAR(20) NOT NULL default `draft_generated`
   - `source_document_ids` UUID[] (or JSONB) NOT NULL default `[]`
   - `source_chunk_ids` UUID[] (or JSONB) NOT NULL default `[]`
   - `grounded` BOOLEAN NOT NULL default false
   - `model_name` VARCHAR(80) NOT NULL
   - `prompt_version` VARCHAR(40) NOT NULL
   - `rag_query_id` UUID NULL FK → rag_queries (provenance link to Spec 009)
   - `approved_by` UUID NULL FK → users
   - `approved_at` TIMESTAMPTZ NULL
   - `created_at`, `updated_at` TIMESTAMPTZ
2. **Indexes**: `(tenant_id, message_id)` for per-message listing; `(message_id, created_at)` for newest-first; `(tenant_id, status)` for review queues.
3. **SQLAlchemy model** `SuggestedReply` in `models/suggested_reply.py` with relationship to `Message`.
4. **Enum** `SuggestedReplyStatus` as constrained strings (portable + evolvable), validated at the boundary.
5. **Array/JSONB choice** — store source id lists as JSONB (portable) or PG `uuid[]`; document the choice; both query the message's tenant only.

---

## AI Prompt / Service Tasks

1. **Prompt versioning** — `PROMPT_VERSION` recorded on every draft; grounded and refusal templates versioned together.
2. **Grounded template** — instruct the model to answer using only the provided source snippets and to reference them; forbid asserting facts not in snippets.
3. **Refusal template** — when no sources: produce a polite "this isn't covered in our uploaded documents; we'll confirm / recommend human review" message; never invent policy/price/availability.
4. **Tone parameterisation** — inject risk level/flag; high-risk → careful/empathetic + optional escalation suggestion; low-risk → friendly/efficient.
5. **Output bounding** — cap reply length (`REPLY_MAX_CHARS`); concise, professional.
6. **Generator abstraction** — swap LLM without touching the service; deterministic stub for tests; provenance (`model_name`) recorded.
7. **Source-citation validation** — post-generation, ensure any cited source ids ⊆ the retrieval result; drop/flag fabricated citations (GR-05).

---

## RAG Integration Tasks

1. **Consume Spec 009** — call `rag_service.query(message text, message_id)` (or read the latest stored `RagQuery`/results) to obtain tenant-scoped sources + status; never bypass tenant filtering.
2. **Status-driven branch** — `grounded` → use sources; `no_source`/`no_documents` → refusal; `failed` → error/retry.
3. **Provenance link** — store `rag_query_id` + the exact `source_document_ids`/`source_chunk_ids` used.
4. **Snippet bounding** — pass only the top-k bounded snippets (`REPLY_SOURCE_SNIPPET_LIMIT`) into the prompt.
5. **Tenant guarantee** — rely on Spec 009's single tenant-filtered retriever; assert all returned source ids belong to the message tenant before prompting (defence in depth).

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/messages/{message_id}/suggested-replies` | POST | staff, manager | Generate a new draft |
| `/api/messages/{message_id}/suggested-replies` | GET | staff, manager | List drafts for a message |
| `/api/suggested-replies/{reply_id}` | GET | staff, manager | Get one reply |
| `/api/suggested-replies/{reply_id}` | PATCH | staff, manager | Edit text (non-terminal) |
| `/api/suggested-replies/{reply_id}/approve` | POST | staff, manager | Approve (human-accept; no send) |
| `/api/suggested-replies/{reply_id}/reject` | POST | staff, manager | Reject |

- All resolve tenant first (404/403) per SR-05; `tenant_id`/`approved_by` from JWT only.
- State-machine guards return 422 `INVALID_STATE_TRANSITION`.
- Consistent `error_code` payloads (see contracts).

---

## Frontend Integration Tasks

1. **`api/suggestedReplies.ts`** — typed client: `generate(messageId)`, `list(messageId)`, `get(id)`, `edit(id, text)`, `approve(id)`, `reject(id)`.
2. **`types/suggestedReply.ts`** — `SuggestedReplyStatus`, `ReplySource`, `SuggestedReply` TS types.
3. **Detail integration (Spec 005)** — replace the "Suggested Reply" placeholder with a real `SuggestedReplyPanel`: shows effective text (edited else generated), status badge, grounded/refusal indicator, source list, and a "Generate" button.
4. **`components/replies/ReplyEditor.tsx`** — editable textarea (prefilled with effective text), Save (edit), Approve, Reject buttons; disabled in terminal states; empty-text guard.
5. **`components/replies/ReplySources.tsx`** — lists source document title/type + snippet (reuses Spec 009 source display).
6. **States** — no-reply-yet (Generate CTA), generating, draft, edited, approved (shows reviewer + time), rejected, refusal (ungrounded notice), precondition-missing (prompt to run upstream), model-unavailable.

---

## Testing Tasks

**Backend integration** — `tests/integration/test_suggested_replies.py`:
- Generate grounded draft + sources (AC-01, AC-02); refusal on no source (AC-03); no uncited facts (AC-04)
- High-risk careful tone + no escalation/task (AC-05)
- Edit (AC-06); approve records reviewer + no send (AC-07); reject (AC-08); invalid transitions (AC-09)
- Tenant isolation (AC-10); sources tenant-only (AC-11)
- Generate + list (AC-12); get + cross-tenant (AC-13)
- Platform Admin 403 (AC-14); no send path (AC-15); multiple drafts + approved not overwritten (AC-16)
- Precondition missing → error (AC-18)

**Unit** — `tests/unit/test_reply_prompt.py` (grounded vs refusal template selection, tone by risk, snippet bounding, prompt_version) and `tests/unit/test_reply_service.py` (state machine, cited-source ⊆ retrieval, effective-text rule).

**Frontend** — render/interaction: panel for grounded vs refusal; editor enabled only in non-terminal; approve/reject update; sources listed (AC-17).

**Eval** — `tests/eval/test_reply_grounding.py`: on the demo corpus, grounded replies cite the right tenant source and refusal fires for unsupported questions (Examples 1–3); verify no cross-tenant source ever appears.

---

## Build Order

1. **DB + model** — Alembic migration + `SuggestedReply` model + status enum.
2. **Schemas** — Pydantic models + enum + `ReplySource`.
3. **Prompt + generator** — `ai/reply_prompt.py` (grounded/refusal/tone) + `ai/reply_generator.py` (interface + stub) + unit tests.
4. **Service** — `suggested_reply_service` (generate with precondition + grounding branch + citation validation; edit/approve/reject state machine) + unit tests.
5. **RAG/upstream wiring** — consume 006/007/009; provenance link; tenant assertion.
6. **API** — six endpoints + router mount + error/state mapping; integration tests.
7. **Frontend** — types + API client → SuggestedReplyPanel (replace placeholder) → ReplyEditor + ReplySources → states.
8. **Validation + eval** — run the 5-scenario quickstart (pricing grounded, cancellation high-risk grounded, unsupported refusal, high-risk complaint tone, tenant isolation); run eval; confirm all 18 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/010-suggested-replies/
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
│   │   └── suggested_replies.py          # 6 endpoints
│   ├── services/
│   │   └── suggested_reply_service.py    # generate / list / get / edit / approve / reject
│   ├── ai/
│   │   ├── reply_generator.py            # LLM interface + deterministic stub
│   │   └── reply_prompt.py               # versioned grounded/refusal/tone prompt builder
│   ├── models/
│   │   └── suggested_reply.py            # SuggestedReply ORM model
│   └── schemas/
│       └── suggested_reply.py            # Pydantic + SuggestedReplyStatus enum + ReplySource
├── alembic/versions/
│   └── 00xx_create_suggested_replies.py
└── tests/
    ├── integration/
    │   └── test_suggested_replies.py
    ├── unit/
    │   ├── test_reply_prompt.py
    │   └── test_reply_service.py
    └── eval/
        └── test_reply_grounding.py

frontend/
└── src/
    ├── api/
    │   └── suggestedReplies.ts
    ├── types/
    │   └── suggestedReply.ts
    └── components/replies/
        ├── SuggestedReplyPanel.tsx       # replaces Spec 005 "Suggested Reply" placeholder
        ├── ReplyEditor.tsx
        └── ReplySources.tsx
```

Modified files:

```
backend/app/main.py                          # mount suggested-replies router
backend/app/core/config.py                   # REPLY_* settings
backend/app/services/conversation_service.py # include latest suggested reply in detail (or dedicated fetch)
frontend/src/pages/ConversationDetailPage    # render SuggestedReplyPanel (replace placeholder)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–009. A dedicated `backend/app/ai/` package holds the prompt builder + generator interface so the LLM and prompt can evolve (versioned) without touching the service/API; the service enforces grounding/refusal and the status state machine, keeping the "no invented answers / no auto-send / no side effects" guarantees in one place.
