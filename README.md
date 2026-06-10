## Local Docker Setup

EventSense AI includes a Docker Compose setup for local development and demos. It starts PostgreSQL 16 with pgvector, Redis, the FastAPI backend, and a one-shot Alembic migration service.

### Fresh Clone

Create a local environment file:

```bash
cp .env.example .env
```

Start the full stack:

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`. Check it with:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

### Step-by-step Startup

If you want to run migrations explicitly:

```bash
docker compose up -d postgres redis
docker compose run --rm migrate
docker compose up api
```

### Useful Commands

Run migrations:

```bash
docker compose run --rm migrate
```

View API logs:

```bash
docker compose logs -f api
```

Connect to PostgreSQL:

```bash
docker compose exec postgres psql -U eventsense -d eventsense_ai
```

Run backend tests inside Docker:

```bash
docker compose run --rm api pytest
```

Stop the stack:

```bash
docker compose down
```

Stop the stack and remove database volumes:

```bash
docker compose down -v
```

### AI Suggested Replies

Suggested replies are staff-review drafts only. They are never sent to clients
automatically. The backend generates them from the latest inbound client message
by default, grounds the wording in the authenticated tenant's RAG documents, and
returns a refusal/staff-review draft when uploaded documents do not support an
answer.

The feature exposes:

- `POST /api/v1/conversations/{conversation_id}/suggested-reply`
- `GET /api/v1/conversations/{conversation_id}/suggested-replies`
- `GET /api/v1/suggested-replies/{reply_id}`
- `PATCH /api/v1/suggested-replies/{reply_id}`
- `GET /api/v1/conversations/{conversation_id}/detail`, which includes the
  latest `suggested_reply` when one exists

Manual demo flow:

```bash
# Use 8088 if you want to match scripts/seed_rag_documents.sh's default.
API_HOST_PORT=8088 docker compose up -d --build
curl http://localhost:8088/health

API_BASE_URL=http://localhost:8088 scripts/seed_rag_documents.sh

TOKEN="$(
  curl -s -X POST http://localhost:8088/auth/token \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@elegant-weddings.demo","password":"demo-password-1","tenant_slug":"elegant-weddings"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"

SIMULATED="$(
  curl -s -X POST http://localhost:8088/api/v1/simulator/messages \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"client_name":"Suggested Reply Demo","client_contact":"+96170100200","body":"Is the deposit refundable after booking confirmation?"}'
)"
CONVERSATION_ID="$(printf '%s' "${SIMULATED}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["conversation_id"])')"

curl -s -X POST "http://localhost:8088/api/v1/conversations/${CONVERSATION_ID}/suggested-reply" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool

curl -s "http://localhost:8088/api/v1/conversations/${CONVERSATION_ID}/detail" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool

REPLY_ID="<reply id from generate response>"
curl -s -X PATCH "http://localhost:8088/api/v1/suggested-replies/${REPLY_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"status":"approved"}' | python3 -m json.tool
```

For an unsupported question, create another simulator message such as
`Can you book my honeymoon flight?` and generate a suggested reply for that
conversation. The response should have `answer_supported=false`, mention that
there is not enough information in uploaded company documents, and ask staff to
review instead of inventing a policy.

### Ports

PostgreSQL is mapped to host port `5433` to avoid conflicts with a local Mac PostgreSQL on `5432`. Inside Docker, services still use `postgres:5432`.

Redis maps host port `6379` by default. If that port is already in use, set `REDIS_HOST_PORT` in `.env`, for example:

```bash
REDIS_HOST_PORT=6380
```

### Smoke Test Checklist

1. `cp .env.example .env`
2. `docker compose up -d postgres redis`
3. `docker compose run --rm migrate`
4. `docker compose up api`
5. `curl http://localhost:8000/health`

Real secrets should stay in `.env`; `.env.example` is only a template.
