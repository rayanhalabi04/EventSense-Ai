# Implementation Plan: Dockerized Stack

**Branch**: `017-dockerized-stack` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/017-dockerized-stack/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): demo tenants + seed; tenant-scoped data
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): demo login for the smoke test
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): calibrated-SVM joblib artifact loaded at startup
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/plan.md): pgvector + `no_source` refusal
- [Spec 015 — Evaluation](../015-evaluation/plan.md): consumes the `docker_smoke` artifact

---

## Summary

Complete and formalize the container stack so the whole project runs with one command and is provably healthy. The existing `docker-compose.yml` already defines `postgres` (pgvector), `redis`, `migrate`, and `api`; this feature adds a `seed` one-shot service, a `frontend` service + `frontend/Dockerfile`, a backend `GET /health` readiness endpoint, and a documented smoke test (`scripts/smoke_test.sh`) that emits a JSON artifact for Spec 015. No application business logic changes — this is packaging, health-gating, seeding, and verification.

---

## Technical Approach

- **Compose ordering**: `postgres (healthy) → migrate (completed) → seed (completed) → api (healthy) → frontend`. Use `depends_on: { condition: service_healthy | service_completed_successfully }` (already used for postgres/migrate; extend to seed).
- **pgvector**: keep `pgvector/pgvector:pg16`; ensure an early Alembic migration runs `CREATE EXTENSION IF NOT EXISTS vector` (verify it exists in Spec 009's migration; add an init migration only if missing).
- **Health endpoint**: add `GET /health` to the FastAPI app doing cheap checks — `SELECT 1`, `SELECT extname FROM pg_extension WHERE extname='vector'`, Alembic head vs DB revision, and classifier load state from the loaded model singleton. Returns `200` when all ok, `503` otherwise. No auth (readiness probe), no secret values.
- **Seed service**: reuse the Spec 001 seed entrypoint as a one-shot compose service (`command: python -m app.seed` or the existing seed CLI), idempotent (upsert by slug).
- **Frontend image**: `frontend/Dockerfile` (Node 20 → Vite). Dev target runs `vite --host` with `VITE_API_URL` from env; an optional `build` stage produces static assets served by `nginx`/`vite preview` (documented, not required).
- **Smoke test**: a POSIX `bash` script using `curl` + `jq` (or a small `python` script) that: waits for `/health`; logs in a demo user (`/auth/login`); posts a simulated message and polls its classification; runs a tenant-scoped RAG query for a no-doc tenant and asserts `no_source`. Prints `[PASS]/[FAIL]` per check, writes `eval-artifacts/docker_smoke.json`, exits non-zero on any failure. A `make smoke` target wraps it.
- **Secrets**: `.env.example` already lists variables; ensure the JWT secret default is clearly a placeholder and document setting a local value. No secrets in images (Dockerfiles copy code + requirements only).
- **Artifact availability**: backend image `COPY . .` already includes code; ensure `data/intent_classifier/` artifact path resolves (either copy the artifact into the image build context or mount `./data` read-only for the demo). Decide via `INTENT_CLASSIFIER_ARTIFACT_PATH`.

---

## Infrastructure Tasks

1. **`frontend/Dockerfile`** — Node 20 slim; install deps; dev command `vite --host 0.0.0.0 --port 5173`; optional `build` stage.
2. **`docker-compose.yml`** — add `frontend` service (build `./frontend`, `VITE_API_URL`, port `5173`, depends on `api`); add `seed` one-shot service (build `./backend`, depends on `migrate` completed); make `api` depend on `seed` completed.
3. **`backend` `GET /health`** — readiness endpoint (db/pgvector/migration/classifier); mount router in `main.py`; no auth; no secret values.
4. **pgvector init** — confirm/ensure `CREATE EXTENSION IF NOT EXISTS vector` in the earliest migration; add an init migration only if absent.
5. **Artifact handling** — ensure the calibrated-SVM joblib resolves at `INTENT_CLASSIFIER_ARTIFACT_PATH` inside the api/migrate images (copy into context or mount `./data:/app/data:ro`).
6. **`.env.example`** — verify every compose-referenced variable is present with a safe default; add `VITE_API_URL`, demo smoke credentials (`SMOKE_USER_EMAIL`, `SMOKE_TENANT_SLUG`) with placeholders.
7. **`.dockerignore`** — ensure `backend/.dockerignore` (present) excludes venvs/caches; add `frontend/.dockerignore` (node_modules, dist).

---

## Smoke-Test Tasks

1. **`scripts/smoke_test.sh`** — health → login → classify → no-doc RAG `no_source`; per-check pass/fail; writes `eval-artifacts/docker_smoke.json`; non-zero exit on failure; never prints secrets/env.
2. **`Makefile`** target `smoke` (and `up`, `down`, `reset`) wrapping compose + the smoke script.
3. **JSON result schema** — `{ checks: [{name, passed, detail}], passed: bool, started_at, completed_at }`; consumed by Spec 015 `docker_smoke`.

---

## Testing Tasks

- **Compose config validation** — `docker compose config` parses; dependency conditions present.
- **Health endpoint unit/integration** — ok path returns 200 with all subchecks; a forced failure (no pgvector / missing artifact) returns 503 with the failing subcheck.
- **Smoke pass** — full run on a healthy stack exits 0 and writes the artifact.
- **Smoke fail** — stop postgres (or unset the artifact path) → smoke exits non-zero naming the failing check; no false pass.
- **Idempotent seed** — run the seed service twice → no duplicate tenants/users.
- **Reset** — `down -v` then `up` re-migrates + re-seeds; normal restart persists data.
- **Secret scan** — grep built images/`/health`/smoke output for secret values → none.

---

## Build Order

1. **Backend `/health`** endpoint + classifier/pgvector/migration subchecks.
2. **Seed service** wired into compose (idempotent) + artifact path resolution.
3. **Frontend Dockerfile + compose service** (dev target) reachable from the browser.
4. **Smoke test script** + `Makefile` targets + JSON artifact.
5. **Docs** — quickstart (one-command run, smoke, reset) + `.env.example` completeness.
6. **Validation** — clean-checkout run; smoke pass + induced fail; reset; secret scan.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/017-dockerized-stack/
├── plan.md
├── spec.md
├── quickstart.md
├── tasks.md
└── checklists/
    └── requirements.md
```

> No `data-model.md` or `contracts/api-contracts.md` — this feature adds one read-only `GET /health` endpoint (documented inline) and no new persisted entities.

### Source Code Layout

New files:

```
frontend/Dockerfile
frontend/.dockerignore
scripts/smoke_test.sh
Makefile
backend/app/api/v1/health.py            # GET /health readiness endpoint
```

Modified files:

```
docker-compose.yml                      # add frontend + seed services; api depends on seed
.env.example                            # VITE_API_URL + smoke creds placeholders
backend/app/main.py                     # mount /health router
backend/alembic/versions/<earliest>     # ensure CREATE EXTENSION vector (only if missing)
```

**Structure Decision**: Compose-based local/CI stack (FastAPI + React + Postgres/pgvector), formalizing the existing compose file. The only application change is an unauthenticated read-only `/health` readiness endpoint; everything else is packaging, ordering, seeding, and a smoke test.
