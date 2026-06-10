# Requirements Checklist: Dockerized Stack

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-10
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (one-command reproducible, demoable stack)
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, Operational rules, Edge/Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed (no k8s/cloud/business-logic changes)

---

## Functional Requirements

- [ ] One-command compose brings up postgres/migrate/api/frontend (+ optional redis/seed) (FR-001, AC-01)
- [ ] pgvector image + `vector` extension created before RAG use (FR-002, AC-05)
- [ ] `migrate` runs `alembic upgrade head` and gates `api` (FR-003, AC-03)
- [ ] Idempotent demo seed (two tenants + managers) (FR-004, AC-04)
- [ ] `GET /health` reports db/pgvector/migration/classifier (FR-005, AC-02)
- [ ] Health checks + dependency ordering on services (FR-006, AC-03)
- [ ] Config from `.env`; `.env.example` complete with safe defaults, no real secrets (FR-007, AC-08)
- [ ] No secrets baked into images; classifier artifact at configured path (FR-008, AC-08, AC-09)
- [ ] Documented smoke test (health/login/classify/no-doc-RAG) with non-zero exit on failure (FR-009, AC-06)
- [ ] Smoke emits JSON consumable by Spec 015 `docker_smoke`; no secret leakage (FR-010, AC-07, AC-12)
- [ ] Clean reset (`down -v` → `up` re-migrate + re-seed); restart persists data (FR-011, AC-10)
- [ ] Frontend service serves app + reaches backend via env URL (FR-012, AC-11)
- [ ] Quickstart docs runnable by a newcomer (FR-013)

---

## Operational / Security Requirements

- [ ] No secrets in images or VCS; `.env.example` placeholders only (OR-01, AC-08)
- [ ] Fail fast on missing pgvector / failed migration / missing artifact (OR-02, AC-05, AC-09)
- [ ] Health-gated startup (dependents wait on health/completion) (OR-03, AC-03)
- [ ] Idempotent seed (OR-04, AC-04)
- [ ] No secret values in `/health` or smoke output (OR-05, AC-12)
- [ ] Smoke test uses tenant-scoped calls; isolation preserved (OR-06)

---

## Edge Cases Covered

- [ ] pgvector extension missing → fail fast
- [ ] Port collisions → env-configurable ports, documented
- [ ] Migration failure → `api` does not start; smoke reports it
- [ ] Classifier artifact absent → fail fast / `classifier: missing`
- [ ] Re-running `up` → idempotent seed, persisted volume
- [ ] `down -v` → clean re-migrate + re-seed
- [ ] Frontend dev vs static build documented
- [ ] Slow first build → generous health-check retries

---

## Implementation Readiness

- [ ] Build order defined (health → seed/artifact → frontend → smoke → docs → validate)
- [ ] No new persisted entities (only read-only `/health`) — no data-model/contracts needed
- [ ] Smoke-test JSON schema defined and aligned with Spec 015 `docker_smoke`
- [ ] Validation covers smoke pass + induced fail, reset, idempotent seed, secret scan
