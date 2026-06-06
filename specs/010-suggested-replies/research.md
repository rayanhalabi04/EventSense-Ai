# Research: Suggested Replies

**Branch**: `010-suggested-replies` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Generation Behind an Interface (LLM in prod, stub in tests)

**Decision**: Define a `ReplyGenerator` interface (`generate(context) -> text`, exposes `model_name`, `prompt_version`). Production uses an LLM; tests use a deterministic stub. Generation failure raises `GenerationUnavailable` → 503, no malformed draft stored.

**Rationale**:
- The reply text is inherently generative, but the surrounding logic (precondition gate, grounding/refusal, state machine, tenant scoping) is deterministic and must be testable without an LLM.
- The interface lets the model evolve (or swap providers) without touching the service/API, and `model_name`/`prompt_version` make every draft reproducible at the configuration level.

**Alternatives considered**:
- Template-only replies (no LLM): safe and deterministic but too rigid for natural agency communication; the grounded/refusal *templates* are still used as guardrails, with the LLM filling in tone. Hybrid chosen.
- Hard-coding a specific provider in the service: couples the feature to one vendor and breaks test isolation; rejected.

---

## Decision 2: Grounding & Refusal Enforced in the Service, Not Just the Prompt

**Decision**: The service decides grounded vs refusal from the Spec 009 RAG **status** before/around generation. `grounded` → use + cite sources; `no_source`/`no_documents` → refusal path (no invented facts, recommend human review). After generation, cited source ids are validated to be a subset of the retrieval result (drop/flag fabricated citations).

**Rationale**:
- Prompts alone don't guarantee an LLM won't hallucinate. Making the refusal a **code path** (not a polite request to the model) is the only way to honour the spec's "must not invent" guarantee (FR-004, GR-02).
- Post-hoc citation validation (GR-05) closes the loop: even if the model cites something, only real retrieved sources are recorded.

**Alternatives considered**:
- Trust the prompt to refuse: brittle; LLMs override instructions under pressure. Rejected as the sole mechanism.
- Block generation entirely when ungrounded: too coarse — a polite "not in our documents, we'll confirm" is useful and is the spec's required behaviour. Chosen over a hard error.

---

## Decision 3: Consume Upstream Signals; Enforce a Precondition Gate

**Decision**: Generation requires the message to already have intent (006), risk (007), and a RAG retrieval (009). If any is missing → 409 `PRECONDITION_NOT_MET`. The service reads existing results (and may trigger a RAG query for the message) rather than re-implementing classification/risk/retrieval.

**Rationale**:
- The MVP workflow is ordered (classify → risk → RAG → reply); the draft quality depends on those signals. Failing loudly when they're missing prevents low-quality, ungrounded guesses.
- Reusing upstream services keeps this feature thin and avoids logic duplication/drift.

**Alternatives considered**:
- Auto-run all upstream steps inside generation: convenient but couples features and hides ordering bugs; a precondition error is clearer. (Triggering only the RAG query, which is naturally per-query, is acceptable; classification/risk are message-creation-time concerns.)
- Generate without upstream signals: produces generic, ungrounded text; defeats the purpose. Rejected.

---

## Decision 4: Human-in-the-Loop State Machine, No Auto-Send

**Decision**: Status lifecycle `draft_generated → edited → approved | rejected`. `approved`/`rejected` are terminal; content edits are blocked once terminal. There is **no send endpoint, method, or queue** — `approved` means human-accepted only.

**Rationale**:
- The hard product constraint is "AI never auto-sends; staff must review" (FR-005, SR-06). A strict state machine + the deliberate absence of any send path enforce it structurally.
- Terminal immutability preserves the integrity of an approved/rejected decision (and a clean record for the future audit feature).

**Alternatives considered**:
- A single mutable `status` with free transitions: error-prone (e.g., un-rejecting); explicit allowed transitions are safer.
- Including a send action gated by a flag: even gated, it violates scope and risks accidental sends; excluded entirely.

---

## Decision 5: Preserve Original Draft; Edits in a Separate Field

**Decision**: `generated_text` is immutable once stored; staff edits live in `edited_text`. The **effective text** is `edited_text` if present, else `generated_text`. Editing sets status `edited`.

**Rationale**:
- Keeping the AI's original separate from the human edit gives provenance (what the AI said vs what the human accepted) — valuable for trust, the audit feature, and future model evaluation.
- A simple "effective text" rule keeps the UI and any downstream consumer unambiguous.

**Alternatives considered**:
- Overwrite text in place: loses the original AI output and its provenance; rejected.
- Full edit history table: richer but beyond MVP; the original + latest-edit pair suffices (regeneration creates a new row anyway).

---

## Decision 6: Multiple Drafts per Message (regeneration creates new rows)

**Decision**: Each generation creates a new `SuggestedReply` row. The latest draft is shown; prior `approved`/`rejected` rows are retained. An `approved` reply is never overwritten by regeneration.

**Rationale**:
- Staff often want to try again; keeping attempts as separate rows preserves history and prevents clobbering a human-approved decision (FR-015, AC-16).
- Avoids a destructive upsert that would lose provenance.

**Alternatives considered**:
- One row per message, overwrite on regenerate: simpler but destroys history and could overwrite an approved reply; rejected.

---

## Decision 7: Risk-Driven Tone via Prompt Parameterisation

**Decision**: The prompt is parameterised by the Spec 007 risk level/flag. High-risk → careful, empathetic, de-escalating, with an optional "consider manager escalation" note. Low-risk → friendly/efficient. No escalation entity is created.

**Rationale**:
- Tone matters most exactly when risk is high (complaints, cancellations, payment disputes). Driving tone from the existing risk signal reuses upstream work and keeps behaviour consistent.
- The escalation *note* is text only; performing escalation is a separate feature (SR-07).

---

## Decision 8: Tenant-Only Grounding by Construction

**Decision**: Grounding sources come exclusively from Spec 009's tenant-scoped retrieval for the message's tenant. Before prompting, the service asserts every source id belongs to the message tenant (defence in depth). Cross-tenant content can never enter the prompt.

**Rationale**:
- Spec 009 already guarantees tenant-scoped retrieval; this feature must not reintroduce a leak by mixing contexts. The explicit assertion is cheap insurance for the strongest guarantee (SR-03, GR-03, FR-013).

---

## Decision 9: Provenance Recording (model + prompt + sources + RAG query)

**Decision**: Every draft records `model_name`, `prompt_version`, `source_document_ids`, `source_chunk_ids`, and `rag_query_id`. Reviewer identity (`approved_by`) + `approved_at` recorded on approval.

**Rationale**:
- Auditability and reproducibility: the exact generation configuration and grounding evidence are captured, which the later audit-log feature and model evaluation both need.
- LLM text isn't bit-reproducible, but the *setup* is — recording the inputs makes outputs explainable.

---

## Decision 10: Single-Message Drafting (no multi-turn) for MVP

**Decision**: Generate a reply to one client message using its own context; no conversation-thread synthesis or multi-turn memory for MVP.

**Rationale**:
- The inbox/detail model is message-centric; single-message drafting matches the workflow and keeps prompts bounded and grounded. Multi-turn is a future enhancement.

---

## Resolved Configuration Defaults

| Setting | Default | Purpose |
|---------|---------|---------|
| `REPLY_MODEL_NAME` | `gpt-style-v1` (configurable) | Recorded on every draft |
| `REPLY_PROMPT_VERSION` | `reply-prompt-v1` | Versioned prompt set (grounded + refusal) |
| `REPLY_MAX_CHARS` | `1200` | Concise reply bound |
| `REPLY_SOURCE_SNIPPET_LIMIT` | `4` | Max RAG snippets injected into the prompt |

> Effective text = `edited_text` if present else `generated_text`. Grounded = non-empty source ids.
