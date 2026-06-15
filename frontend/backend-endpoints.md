# EventSense AI Backend Endpoints

Backend source: `backend/app/main.py` and route modules under `backend/app/api/`.

Default local API base URL: `http://localhost:8000`

Most `/api/v1/...` routes require a Bearer JWT created by the auth endpoints. Tenant scoping and role checks are enforced through the backend tenant context.

## Runtime Structure

| Area | Path | Purpose |
| --- | --- | --- |
| App entrypoint | `backend/app/main.py` | FastAPI app setup, CORS, exception handlers, router mounts |
| API routes | `backend/app/api/`, `backend/app/api/v1/` | HTTP endpoint definitions |
| Core | `backend/app/core/` | Config, database, auth/security, tenant context |
| Models | `backend/app/models/` | SQLAlchemy models |
| Schemas | `backend/app/schemas/` | Pydantic request and response schemas |
| Repositories | `backend/app/repositories/` | Database access layer |
| Services | `backend/app/services/` | Domain logic, RAG, LLM, guardrails, memory, simulator |
| Migrations | `backend/alembic/` | Alembic migrations |
| Tests | `backend/tests/` | Integration and unit tests |

## Infrastructure

| Service | Default |
| --- | --- |
| API | `http://localhost:8000` |
| PostgreSQL + pgvector | host port `5433`, container port `5432` |
| Redis | host port `6379` |
| Frontend CORS origins | `http://localhost:5173`, `http://localhost:4173` |

## Auth

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| `POST` | `/auth/token` | Public | Login with `email`, `password`, `tenant_slug`; returns bearer token |
| `GET` | `/auth/me` | Bearer token | Current user |
| `POST` | `/auth/refresh` | Bearer token | Refresh access token |
| `POST` | `/auth/logout` | Bearer token | Emits logout audit event |
| `POST` | `/api/v1/auth/login` | Public | Legacy login; `tenant_slug` is optional |

## Health

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | Checks DB, pgvector, migration state, classifier artifact |

## Tenants

| Method | Endpoint | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/tenants/me` | `staff`, `manager` | Current tenant |
| `GET` | `/api/v1/admin/tenants` | `platform_admin` | List tenants |

## Conversations

| Method | Endpoint | Roles | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v1/conversations` | `staff`, `manager` | Create conversation |
| `GET` | `/api/v1/conversations` | `staff`, `manager` | List tenant conversations |
| `GET` | `/api/v1/conversations/{conversation_id}` | `staff`, `manager` | Get conversation |
| `GET` | `/api/v1/conversations/{conversation_id}/detail` | `staff`, `manager` | Conversation with messages, replies, tasks, escalations, audit context |

## Messages

| Method | Endpoint | Roles | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v1/conversations/{conversation_id}/messages` | `staff`, `manager` | Create message in conversation |
| `GET` | `/api/v1/conversations/{conversation_id}/messages` | `staff`, `manager` | List messages in conversation |

## Suggested Replies

| Method | Endpoint | Roles | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v1/conversations/{conversation_id}/suggested-reply` | `staff`, `manager` | Generate suggested reply |
| `GET` | `/api/v1/conversations/{conversation_id}/suggested-replies` | `staff`, `manager` | List suggested replies for conversation |
| `GET` | `/api/v1/suggested-replies/{reply_id}` | `staff`, `manager` | Get suggested reply |
| `PATCH` | `/api/v1/suggested-replies/{reply_id}` | `staff`, `manager` | Update suggested reply status/content |

## Inbox

| Method | Endpoint | Roles | Query Parameters |
| --- | --- | --- | --- |
| `GET` | `/api/v1/inbox` | `staff`, `manager` | `status`, `source`, `direction`, pagination fields from `InboxFilters` |
| `GET` | `/api/v1/inbox/summary` | `staff`, `manager` | None |
| `GET` | `/api/v1/inbox/messages` | `staff`, `manager` | `status`, `source`, `direction`, `page`, `page_size` |

## Simulator

| Method | Endpoint | Roles | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v1/simulator/messages` | `staff`, `manager` | Simulate inbound WhatsApp-style client message |
| `GET` | `/api/v1/simulator/conversations` | `staff`, `manager` | List simulator conversation summaries |

## Tasks

| Method | Endpoint | Roles | Query Parameters |
| --- | --- | --- | --- |
| `POST` | `/api/v1/tasks` | `staff`, `manager` | None |
| `GET` | `/api/v1/tasks` | `staff`, `manager` | `status`, `conversation_id`, `assigned_to_user_id` |
| `GET` | `/api/v1/tasks/{task_id}` | `staff`, `manager` | None |
| `PATCH` | `/api/v1/tasks/{task_id}` | `staff`, `manager` | None |

## Escalations

| Method | Endpoint | Roles | Query Parameters |
| --- | --- | --- | --- |
| `POST` | `/api/v1/escalations` | `staff`, `manager` | None |
| `GET` | `/api/v1/escalations` | `staff`, `manager` | `status`, `conversation_id`, `assigned_manager_user_id` |
| `GET` | `/api/v1/escalations/{escalation_id}` | `staff`, `manager` | None |
| `PATCH` | `/api/v1/escalations/{escalation_id}` | `manager` | None |

## Documents

| Method | Endpoint | Roles | Query Parameters / Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v1/documents` | `manager`, `platform_admin` | Create document from JSON payload |
| `POST` | `/api/v1/documents/upload` | `manager`, `platform_admin` | Multipart upload; `.txt` UTF-8 only; fields: `file`, `document_type`, optional `title` |
| `GET` | `/api/v1/documents` | `staff`, `manager`, `platform_admin` | `document_type`, `status`, `search` |
| `GET` | `/api/v1/documents/{document_id}` | `staff`, `manager`, `platform_admin` | None |
| `PATCH` | `/api/v1/documents/{document_id}` | `manager`, `platform_admin` | Update document |
| `DELETE` | `/api/v1/documents/{document_id}` | `manager`, `platform_admin` | Archive document |

## RAG

| Method | Endpoint | Roles | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v1/rag/query` | `staff`, `manager` | Tenant-scoped retrieval with guardrails; supports `query`, `top_k`, `document_type_filter` |

## Audit Logs

| Method | Endpoint | Roles | Query Parameters |
| --- | --- | --- | --- |
| `GET` | `/api/v1/audit-logs` | `manager`, `platform_admin` | `limit` from `1` to `500`, `offset` >= `0` |

## Common Auth Header

```http
Authorization: Bearer <access_token>
```

## Example Login

```bash
curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@elegant-weddings.demo","password":"demo-password-1","tenant_slug":"elegant-weddings"}'
```
