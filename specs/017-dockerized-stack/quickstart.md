# Quickstart: Dockerized Stack

**Branch**: `017-dockerized-stack`

Bring the entire EventSense AI stack up with one command and prove it works with the smoke test. Only **Docker + Docker Compose v2** are required on the host.

Steps:
1. Configure `.env`.
2. Build and start the stack.
3. Wait for health.
4. Run the smoke test.
5. Open the app.
6. Reset when needed.

---

## Prerequisites

- Docker + Docker Compose v2 installed and running.
- Free ports (defaults): Postgres `5433`, backend `8000`, frontend `5173`, Redis `6379`. Override in `.env` if taken.
- The trained classifier artifact present under `data/intent_classifier/` (Spec 006).

---

## 1. Configure

```bash
cp .env.example .env
# Set a local JWT secret (any non-default value):
#   JWT_SECRET_KEY=<your-local-secret>
```

`.env.example` documents every variable with safe local defaults — no real secrets are committed.

## 2. Build and start

```bash
docker compose up --build -d
# or:  make up
```

Startup order is health-gated: `postgres → migrate (alembic upgrade head) → seed (demo tenants) → api → frontend`.

## 3. Wait for health

```bash
curl -s http://localhost:8000/health | jq
```

Expect `200` with:

```json
{ "status": "ok", "db": "ok", "pgvector": "ok", "migration": "head", "classifier": "loaded" }
```

If `status` is not `ok`, the failing subcheck names the problem (e.g., `classifier: missing`, `pgvector: missing`).

## 4. Run the smoke test

```bash
./scripts/smoke_test.sh
# or:  make smoke
```

It checks: `/health` → demo login → create a simulated message and confirm it is classified → tenant-scoped RAG query for a no-document tenant returns `no_source`. It prints `[PASS]/[FAIL]` per check, writes `eval-artifacts/docker_smoke.json` (consumed by Spec 015 `docker_smoke`), and exits non-zero on any failure. It never prints secrets or env values.

## 5. Open the app

- Frontend: http://localhost:5173
- Backend docs: http://localhost:8000/docs
- Log in with a seeded demo manager (see `.env` `SMOKE_USER_EMAIL` / tenant slug).

## 6. Reset

```bash
docker compose down            # stop (DB data persists)
docker compose down -v         # destructive: drop DB volume
docker compose up --build -d   # re-migrate + re-seed from scratch
# or:  make reset
```

---

## Demo tenants (seeded)

| Tenant | Slug | Initial user role |
|--------|------|-------------------|
| Elegant Weddings | `elegant-weddings` | manager |
| Royal Events Agency | `royal-events-agency` | manager |

Seeding is idempotent — re-running never duplicates tenants/users.

---

## Troubleshooting

- **Port in use**: change `API_PORT` / frontend / `5433` mapping in `.env` and `docker compose up` again.
- **`pgvector: missing`**: ensure the `pgvector/pgvector:pg16` image is used and the extension migration ran (`docker compose logs migrate`).
- **`classifier: missing`**: confirm `INTENT_CLASSIFIER_ARTIFACT_PATH` resolves inside the container (artifact copied into the image or `./data` mounted).
- **`migrate` failed**: `docker compose logs migrate`; fix the migration and re-run; `api` will not serve until `migrate` completes.
- **Smoke fails on classify/RAG**: confirm the seed ran and the classifier loaded (`/health`).
