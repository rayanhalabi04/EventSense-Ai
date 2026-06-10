# Feature Specification: Dockerized Stack

**Feature Branch**: `017-dockerized-stack`

**Created**: 2026-06-10

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)
- [Spec 015 — Evaluation](../015-evaluation/spec.md)

**Input**: User description: "The whole EventSense AI stack (PostgreSQL+pgvector, backend, migrations, frontend) should run reproducibly with a single command via Docker Compose, with health checks, seeded demo tenants, the trained classifier artifact available, and a documented smoke test that proves the stack is up."

---

## Goal

Make EventSense AI **reproducible and demoable with one command**. A reviewer should be able to clone the repo, copy `.env.example` to `.env`, run `docker compose up`, and get a healthy stack: PostgreSQL with the **pgvector** extension, applied Alembic migrations, seeded demo tenants (Elegant Weddings + Royal Events Agency), the trained intent-classifier artifact loaded by the backend, a healthy FastAPI backend, and the React frontend served. The stack exposes a **health endpoint** and ships a documented **smoke test** that proves the core pipeline works end to end (DB reachable, migrations applied, backend healthy, a message classified, a tenant-scoped RAG query returns the no-source refusal when a tenant has no docs). This feature formalizes and completes the existing `docker-compose.yml` + `backend/Dockerfile` (adding a frontend service, health endpoint, seed step, artifact handling, and the smoke test); it changes **no** application business logic.

---

## Stack Services

| Service | Image / Build | Purpose |
|---------|---------------|---------|
| `postgres` | `pgvector/pgvector:pg16` | PostgreSQL 16 with the pgvector extension (vector store for Spec 009) |
| `redis` | `redis:7-alpine` | Cache / future background-task broker (optional for MVP runtime) |
| `migrate` | build `./backend` | One-shot `alembic upgrade head`; gates the API on a migrated DB |
| `seed` | build `./backend` | One-shot demo seed (tenants + manager users); idempotent |
| `api` | build `./backend` | FastAPI backend (uvicorn); loads the classifier artifact at startup |
| `frontend` | build `./frontend` | React + Vite app (dev server or static build served) |

> `redis` and `seed` are convenience services; the minimum demo path is `postgres → migrate → api (+ frontend)`.

---

## Main Users

| Role | Description |
|------|-------------|
| **Developer / project owner** | Builds and runs the stack locally, runs migrations/seeds, and executes the smoke test before a demo or commit. |
| **Instructor / evaluator** | Clones the repo and brings the stack up with one command to verify the project runs reproducibly. |
| **CI runner** (Spec 018) | Builds images and runs the smoke test as an automated gate. |

---

## User Stories

### User Story 1 — One-Command Reproducible Stack (Priority: P1)

A developer copies `.env.example` to `.env` and runs `docker compose up --build`. PostgreSQL starts with pgvector, migrations run to head, demo tenants are seeded, the backend comes up healthy with the classifier artifact loaded, and the frontend is reachable. The whole stack starts from a clean machine with only Docker installed.

**Why this priority**: Reproducibility is the feature's reason to exist — a reviewer must be able to run the project without a hand-held setup. Every other story builds on a stack that comes up cleanly.

**Independent Test**: On a clean checkout, `cp .env.example .env && docker compose up --build -d`; wait for health; assert `GET /health` returns `200` with `{status: ok, db: ok, pgvector: ok, classifier: loaded}` and the frontend responds on its port.

**Acceptance Scenarios**:

1. **Given** a clean checkout with Docker installed, **When** `docker compose up --build` runs, **Then** `postgres`, `migrate`, `api`, and `frontend` reach a healthy/completed state with no manual steps.
2. **Given** the stack is up, **When** `GET /health` is called, **Then** it returns `200` reporting DB connectivity, the pgvector extension present, migration head applied, and the classifier artifact loaded.
3. **Given** the `migrate` service, **When** it runs, **Then** Alembic upgrades to head before `api` accepts traffic (`api` depends on `migrate` completing successfully).
4. **Given** the demo seed, **When** it runs, **Then** Elegant Weddings + Royal Events Agency and their manager users exist (idempotently — re-running does not duplicate).

---

### User Story 2 — Documented Smoke Test Proves the Pipeline (Priority: P1)

A developer runs a single smoke-test command (script) against the running stack. It checks DB + pgvector, backend health, authenticates a demo user, creates a simulated message and asserts it gets classified, and runs a tenant-scoped RAG query for a tenant with no documents and asserts the `no_source` refusal. It prints a clear pass/fail summary and exits non-zero on failure.

**Why this priority**: "It builds" is not "it works." The smoke test is the evidence the stack is functional, and it is the artifact Spec 015/018 consume. Equal P1.

**Independent Test**: With the stack up, run `./scripts/smoke_test.sh` (or `make smoke`); assert it exits `0`, prints each check's pass/fail, and that a failure (e.g., stopped DB) makes it exit non-zero with a clear message.

**Acceptance Scenarios**:

1. **Given** a running stack, **When** the smoke test runs, **Then** it verifies `/health`, logs in a demo user, classifies a message, and runs a no-doc RAG query expecting `no_source`, reporting pass/fail per check.
2. **Given** a healthy stack, **When** the smoke test completes, **Then** it exits `0` and writes a small machine-readable result (JSON) consumable by Spec 015 (`docker_smoke`).
3. **Given** a broken stack (DB down or migration failed), **When** the smoke test runs, **Then** it exits non-zero and names the failing check; no false "pass".
4. **Given** the smoke test, **When** it runs, **Then** it uses only seeded demo/synthetic data and tenant-scoped calls — it never prints secrets or env values.

---

### User Story 3 — Configuration via Env, Secrets Not Baked In (Priority: P2)

The stack reads configuration from `.env` (DB URL, JWT secret, classifier artifact path, ports). `.env.example` documents every variable with safe local defaults; real secrets are never committed or baked into images. Images are built reproducibly and the backend image contains the classifier artifact (or mounts it) at the configured path.

**Why this priority**: Clean config separation makes the stack portable and safe to share, but the stack still runs with defaults; this hardens rather than enables. P2.

**Independent Test**: Inspect `.env.example` — assert every referenced variable is present with a safe default and no real secret. Build the backend image — assert the classifier artifact is resolvable at `INTENT_CLASSIFIER_ARTIFACT_PATH` and `/health` reports `classifier: loaded`.

**Acceptance Scenarios**:

1. **Given** `.env.example`, **When** copied to `.env`, **Then** the stack runs with safe local defaults and no missing-variable errors.
2. **Given** the built images, **When** scanned, **Then** no real secret/JWT/API key is baked in; secrets come only from `.env`/runtime env.
3. **Given** `INTENT_CLASSIFIER_ARTIFACT_PATH`, **When** the backend starts, **Then** the artifact is found and loaded (or the backend fails fast with a clear message if missing).

---

### Edge Cases

- **pgvector extension missing**: the migrate/init step creates `CREATE EXTENSION IF NOT EXISTS vector`; if the base image lacks it, the stack fails fast with a clear error (no silent vector-less start).
- **Port already in use** (5433/8000/5173): documented in quickstart; ports are env-configurable to avoid collisions.
- **Migrations fail**: `api` does not start (it depends on `migrate` completing successfully); the smoke test reports the migration failure.
- **Classifier artifact absent**: backend fails fast at startup (or `/health` reports `classifier: missing`); the smoke test fails clearly rather than serving a broken classifier.
- **Re-running `up`**: seed is idempotent; volumes persist DB data; no duplicate tenants/users.
- **Clean reset**: `docker compose down -v` removes the DB volume; the next `up` re-migrates and re-seeds from scratch.
- **Frontend build vs dev**: dev uses Vite with the API URL from env; a production-style static build is an optional target (documented), not required for the demo.
- **Slow first build**: image build can be slow on first run; health checks have generous retries so the stack is considered up only when truly healthy.

---

## Requirements

### Functional Requirements

- **FR-001**: The repo MUST provide a `docker-compose.yml` that brings up `postgres` (pgvector), `migrate`, `api`, and `frontend` (plus optional `redis`, `seed`) with one command.
- **FR-002**: `postgres` MUST use a pgvector-capable image and MUST have the `vector` extension available/created before RAG features are exercised.
- **FR-003**: The `migrate` service MUST run `alembic upgrade head` and MUST complete successfully before `api` accepts traffic (dependency ordering + health gating).
- **FR-004**: A demo **seed** MUST create the two demo tenants and their manager users **idempotently** (Spec 001), runnable as a one-shot service or documented command.
- **FR-005**: The backend MUST expose a **health endpoint** (`GET /health`) reporting overall status plus DB connectivity, pgvector presence, migration head, and classifier-artifact load state.
- **FR-006**: Each long-running service MUST define a **health check**; dependents MUST wait on health/completion (`depends_on … condition`).
- **FR-007**: The stack MUST read configuration from `.env`; `.env.example` MUST document every variable with safe local defaults and **no real secrets**.
- **FR-008**: Images MUST NOT bake in real secrets/JWTs/API keys; the trained classifier artifact MUST be available to the backend at `INTENT_CLASSIFIER_ARTIFACT_PATH` (in-image or mounted).
- **FR-009**: The repo MUST provide a documented **smoke test** (script + optional `make` target) that checks `/health`, logs in a demo user, classifies a message, and runs a no-doc tenant-scoped RAG query expecting `no_source`, with per-check pass/fail and a non-zero exit on failure.
- **FR-010**: The smoke test MUST emit a small **machine-readable result** (JSON) consumable by Spec 015 (`docker_smoke`) and MUST NOT print secrets/env values.
- **FR-011**: The stack MUST support a clean reset (`docker compose down -v` → `up` re-migrates + re-seeds) and persist DB data across normal restarts via a named volume.
- **FR-012**: A frontend service MUST build and serve the React app, reading the backend URL from env so it talks to the `api` service.
- **FR-013**: Quickstart documentation MUST cover prerequisites, the one-command start, the smoke test, common ports, and reset — runnable by someone new to the repo.

### Key Entities

- **Compose service** (postgres / redis / migrate / seed / api / frontend): runtime units with health checks + dependency ordering.
- **Health report** (new, read-only): `{ status, db, pgvector, migration, classifier }` returned by `GET /health`.
- **Smoke-test result** (new, artifact): per-check pass/fail + overall, written as JSON for Spec 015.
- **Env configuration**: `.env` / `.env.example` variables (DB URL, JWT secret, ports, artifact path, model version).

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| `.env` | Copied from `.env.example` | DB URL, JWT secret, ports, classifier artifact path/version |
| `docker compose up` | Developer / CI | Brings the stack up (with `--build` on first run) |
| Classifier artifact | `data/intent_classifier/` / image | Loaded by the backend at the configured path (Spec 006) |
| Demo seed data | Seed script (Spec 001) | Demo tenants + manager users |
| Smoke-test command | `scripts/smoke_test.sh` / `make smoke` | Runs the documented pipeline check |

---

## Outputs

| Output | Description |
|--------|-------------|
| Running stack | Healthy postgres + api + frontend (migrated + seeded) |
| Health report | `GET /health` JSON with DB/pgvector/migration/classifier status |
| Smoke-test summary | Per-check pass/fail + overall exit code |
| Smoke-test artifact | JSON result for Spec 015 `docker_smoke` |
| Quickstart docs | One-command run + smoke-test + reset instructions |

---

## Main Workflow

1. **Configure** — `cp .env.example .env` (safe local defaults; set a local JWT secret).
2. **Build + up** — `docker compose up --build`: `postgres` starts and becomes healthy.
3. **Migrate** — the `migrate` service runs `alembic upgrade head` and completes.
4. **Seed** — the demo seed creates the two tenants + managers (idempotent).
5. **Backend up** — `api` starts, loads the classifier artifact, and reports healthy on `/health`.
6. **Frontend up** — `frontend` builds/serves and talks to `api` via the env URL.
7. **Smoke test** — run `scripts/smoke_test.sh`: health → login → classify → no-doc RAG refusal → pass/fail + JSON artifact.
8. **Reset (optional)** — `docker compose down -v` removes data; the next `up` re-migrates + re-seeds.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | `docker compose up --build` brings up postgres/migrate/api/frontend healthy with no manual steps | Clean-checkout run |
| AC-02 | `GET /health` returns 200 with db/pgvector/migration/classifier status | Integration test |
| AC-03 | `migrate` completes before `api` serves traffic (dependency/health gating) | Compose config + run |
| AC-04 | Demo seed creates the two tenants + managers idempotently | Run twice → no duplicates |
| AC-05 | pgvector extension is present/created; RAG vector ops work | Smoke test / integration |
| AC-06 | Smoke test checks health/login/classify/no-doc-RAG and exits 0 on success, non-zero on failure | Smoke run (pass + induced fail) |
| AC-07 | Smoke test writes a JSON result consumable by Spec 015 `docker_smoke` | Artifact review |
| AC-08 | `.env.example` documents all variables with safe defaults; no real secrets committed or baked into images | Repo + image scan |
| AC-09 | Classifier artifact resolvable at the configured path; `/health` reports `classifier: loaded` | Build + health check |
| AC-10 | `down -v` then `up` re-migrates + re-seeds cleanly; normal restart persists data | Reset run |
| AC-11 | Frontend service serves the app and reaches the backend via env URL | Browser/curl check |
| AC-12 | No secrets/env values printed by the smoke test or health endpoint | Output scan |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Demo tenants + seed; tenant-scoped data the smoke test exercises |
| Spec 002 — Authentication and Roles | Required | Demo login used by the smoke test |
| Spec 006 — Intent Classifier | Required | The artifact loaded at startup; classify check in the smoke test |
| Spec 009 — RAG Over Tenant Documents | Required | pgvector; the no-doc `no_source` refusal check |
| Spec 015 — Evaluation | Consumer | `docker_smoke` area consumes the smoke-test artifact |
| Docker + Docker Compose | Required | The only host prerequisite |
| Existing `docker-compose.yml` + `backend/Dockerfile` | Extends | This feature completes them (frontend service, seed, health, smoke) |

---

## Security / Operational Rules

| Rule | Description |
|------|-------------|
| **OR-01: No secrets in images or VCS** | Real secrets/JWTs/API keys live only in `.env`/runtime env; `.env.example` carries safe placeholders. |
| **OR-02: Fail fast, not silently** | Missing pgvector, failed migration, or missing artifact fails the stack/smoke test loudly — never a degraded silent start. |
| **OR-03: Health-gated startup** | Dependents wait on health/completion so the stack is "up" only when truly ready. |
| **OR-04: Idempotent seed** | Re-running the seed never duplicates tenants/users. |
| **OR-05: No secret leakage in diagnostics** | `/health` and the smoke test report status, never secret values. |
| **OR-06: Tenant isolation preserved** | The smoke test uses tenant-scoped calls; it does not bypass the Spec 001 boundary. |

---

## Out of Scope

- **Production orchestration** (Kubernetes, Helm, autoscaling) — Compose is the MVP target.
- **Cloud deployment / managed DB / TLS termination / domain setup** — local + CI demo only.
- **Real WhatsApp API, calendar sync, billing, mobile app, full CRM** — out of scope entirely.
- **Multi-node / HA Postgres, connection pooler (pgbouncer)** — single-node MVP.
- **Background worker/queue runtime** — `redis` is included for future use; no worker is required for the MVP demo.
- **Secret managers (Vault/SSM)** — `.env` is the MVP mechanism; managed secrets are future hardening.
- **Changing any application business logic** — this feature only packages/operationalizes existing features.

---

## Assumptions

- Docker + Docker Compose v2 are the only host prerequisites.
- The existing `docker-compose.yml` (postgres/redis/migrate/api) and `backend/Dockerfile` are the baseline; this feature adds `frontend` + `seed`, the `/health` endpoint, and the smoke test.
- The classifier artifact (Spec 006, calibrated SVM) is present under `data/intent_classifier/` and copied into / mounted by the backend image at `INTENT_CLASSIFIER_ARTIFACT_PATH`.
- The smoke test runs against the running stack (host or CI) and uses seeded demo credentials from env.
- pgvector is provided by the `pgvector/pgvector:pg16` image; the extension is created in an early migration.
- Reset semantics: `down -v` is destructive (drops the DB volume) by design; normal restarts persist data.
