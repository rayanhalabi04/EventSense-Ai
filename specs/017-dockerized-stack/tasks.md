---
description: "Task list for Dockerized Stack feature implementation"
---

# Tasks: Dockerized Stack

**Branch**: `017-dockerized-stack` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/017-dockerized-stack/` (spec.md, plan.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: demo seed (tenants + manager users), idempotent by slug
- Spec 002 — Authentication and Roles: `/auth/login` for the smoke test
- Spec 006 — Intent Classifier: calibrated-SVM joblib artifact + `INTENT_CLASSIFIER_ARTIFACT_PATH`
- Spec 009 — RAG Over Tenant Documents: pgvector + `no_source` refusal
- Spec 015 — Evaluation: consumes `eval-artifacts/docker_smoke.json`

**Tech stack**: Docker Compose v2 · `pgvector/pgvector:pg16` · FastAPI/uvicorn (backend) · React 18 + Vite (frontend, Node 20) · bash + curl + jq smoke test

**No new schema**: this feature adds one read-only `GET /health` endpoint and infra files only.

## Format: `[ID] [P?] [Story?] Description`
- `[P]` = parallelizable (different files, no dependency)
- `[Story]` = the user story the task serves (US1/US2/US3)

---

## Phase 1 — Backend readiness endpoint (US1)

- [ ] T001 [US1] Add `backend/app/api/v1/health.py` — `GET /health` returning `{status, db, pgvector, migration, classifier}`; `200` when all ok else `503`; no auth, no secret values.
- [ ] T002 [US1] Implement subchecks: `SELECT 1` (db), `pg_extension` vector present (pgvector), Alembic DB revision == head (migration), classifier singleton loaded (classifier).
- [ ] T003 [US1] Mount the health router in `backend/app/main.py`.
- [ ] T004 [P] [US1] Unit/integration test: ok path → 200 all-ok; forced failure (no pgvector / missing artifact) → 503 naming the failing subcheck.

## Phase 2 — pgvector + artifact availability (US1/US3)

- [ ] T005 [US1] Confirm the earliest Alembic migration runs `CREATE EXTENSION IF NOT EXISTS vector`; add an init migration only if missing.
- [ ] T006 [US3] Ensure the calibrated-SVM joblib resolves at `INTENT_CLASSIFIER_ARTIFACT_PATH` inside the api/migrate images (copy into build context or mount `./data:/app/data:ro`); decide and document the choice.
- [ ] T007 [P] [US3] Verify the backend fails fast with a clear message (or `/health` reports `classifier: missing`) when the artifact is absent.

## Phase 3 — Compose services: seed + frontend (US1)

- [ ] T008 [US1] Add a `seed` one-shot compose service (build `./backend`, `command` = demo seed, `depends_on: migrate completed`); make `api` depend on `seed` completed.
- [ ] T009 [US1] Create `frontend/Dockerfile` (Node 20 slim; install deps; dev `vite --host 0.0.0.0 --port 5173`; optional `build` stage).
- [ ] T010 [P] [US1] Create `frontend/.dockerignore` (node_modules, dist, .vite).
- [ ] T011 [US1] Add a `frontend` compose service (build `./frontend`, `VITE_API_URL`, port `5173`, `depends_on: api`).
- [ ] T012 [US3] Update `.env.example`: add `VITE_API_URL`, `SMOKE_USER_EMAIL`, `SMOKE_USER_PASSWORD`, `SMOKE_TENANT_SLUG` (placeholders); confirm every compose-referenced variable has a safe default.

## Phase 4 — Smoke test (US2)

- [ ] T013 [US2] Write `scripts/smoke_test.sh`: wait for `/health` → `/auth/login` (demo) → create simulated message + poll classification → tenant-scoped RAG query (no-doc tenant) expecting `no_source`; `[PASS]/[FAIL]` per check; non-zero exit on failure; never print secrets/env.
- [ ] T014 [US2] Emit `eval-artifacts/docker_smoke.json` (`{checks:[{name,passed,detail}], passed, started_at, completed_at}`) for Spec 015 `docker_smoke`.
- [ ] T015 [P] [US2] Add a `Makefile` with `up`, `down`, `reset`, `smoke` targets wrapping compose + the smoke script.

## Phase 5 — Tests + validation

- [ ] T016 [P] `docker compose config` parses; dependency conditions (`service_healthy` / `service_completed_successfully`) present for postgres/migrate/seed/api.
- [ ] T017 Smoke PASS: clean-checkout `up` → smoke exits 0 → artifact written (AC-01, AC-06, AC-07).
- [ ] T018 Smoke FAIL: stop postgres (or unset artifact path) → smoke exits non-zero naming the failing check; no false pass (AC-06).
- [ ] T019 [P] Idempotent seed: run the seed service twice → no duplicate tenants/users (AC-04).
- [ ] T020 [P] Reset: `down -v` then `up` re-migrates + re-seeds; normal restart persists data (AC-10).
- [ ] T021 [P] Secret scan: built images, `/health`, and smoke output contain no secret/env values (AC-08, AC-12).

## Phase 6 — Docs

- [ ] T022 [P] Finalize `quickstart.md` (one-command run, smoke, reset, ports, troubleshooting) and update root `README.md` to point at it.

---

## Dependencies / ordering

- T001–T003 before T004; T005–T007 before the smoke test depends on pgvector + artifact.
- Compose services (T008–T012) before the smoke test (T013–T015) can run end to end.
- Validation (T016–T021) after the stack + smoke exist.
- `[P]` tasks within a phase touch different files and can run in parallel.

## Acceptance mapping

- US1 → AC-01..AC-05, AC-09..AC-11 (stack up, health, migrate gating, seed, pgvector, artifact, frontend)
- US2 → AC-06, AC-07, AC-12 (smoke pass/fail, artifact, no secret leakage)
- US3 → AC-08, AC-09 (env config, no baked secrets, artifact resolvable)
