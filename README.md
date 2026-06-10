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
