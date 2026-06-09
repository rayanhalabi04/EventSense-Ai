# Quickstart: RAG Over Tenant Documents

**Branch**: `009-rag-over-tenant-documents`

This guide walks through the full RAG retrieval flow with the two demo tenants — **Elegant Weddings** and **Royal Events Agency** — and proves that retrieval is strictly tenant-scoped and refuses when no source is relevant.

Flow: **upload → process → embed → query T1 → confirm T1-only → query T2 → confirm T2-only → unsupported query → confirm refuse.**

---

## Prerequisites

- Specs 001–008 implemented and migrated (tenants, auth, messages, detail page, document upload)
- pgvector available in PostgreSQL
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`

---

## Run Migrations (enables pgvector + RAG tables)

```bash
cd backend
alembic upgrade head
# Runs CREATE EXTENSION vector + creates document_chunks, rag_queries, rag_retrieval_results
```

---

## Login (managers of both tenants)

```bash
EW=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@elegant-weddings.demo","password":"manager-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)

RE=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@royal-events.demo","password":"manager-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)
```

---

## Step 1 — Upload tenant documents (Spec 008)

```bash
create_doc () {  # $1=token $2=title $3=type $4=content -> echoes document id
  curl -s -X POST http://localhost:8000/api/documents \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg t "$2" --arg ty "$3" --arg c "$4" '{title:$t, document_type:$ty, content:$c}')" \
    | jq -r .id
}

# Elegant Weddings
EW_DEP=$(create_doc "$EW" "Deposit Policy" "deposit_policy" \
  "A 30% deposit is required to confirm a booking. Deposits are non-refundable within 45 days of the event. Outside 45 days, the deposit is 50% refundable.")
EW_CAN=$(create_doc "$EW" "Cancellation Policy" "cancellation_policy" \
  "Cancellations 90+ days before the event receive a 50% refund of payments beyond the deposit. Within 30 days, no refund is given.")
create_doc "$EW" "Premium Wedding Package" "wedding_packages" \
  "Premium package: full-day coordination, 200 guests, premium florals, 3-course plated dinner." >/dev/null
create_doc "$EW" "Decoration Rules" "decoration_rules" \
  "Open flames are not permitted indoors. All decor must be removed by midnight." >/dev/null

# Royal Events Agency
RE_REF=$(create_doc "$RE" "Refund Policy" "deposit_policy" \
  "Deposits are 25% and fully refundable up to 60 days before the event. Within 60 days, deposits are non-refundable but transferable to a new date.")
create_doc "$RE" "Luxury Wedding Package" "wedding_packages" \
  "Luxury package: two-day event, 350 guests, designer florals, live band, premium bar." >/dev/null
create_doc "$RE" "Catering Policy" "catering_rules" \
  "External caterers must be licensed and approved 30 days in advance. Corkage applies to outside beverages." >/dev/null
create_doc "$RE" "Bridal Entrance Setup Policy" "decoration_rules" \
  "Bridal entrance requires a 6-meter aisle clearance and approved lighting rigging." >/dev/null

echo "EW deposit=$EW_DEP cancellation=$EW_CAN ; RE refund=$RE_REF"
```

---

## Step 2 + 3 — Process documents into chunks + embeddings

```bash
process () { curl -s -X POST http://localhost:8000/api/documents/$2/process \
  -H "Authorization: Bearer $1" | jq '{document_id, status, chunk_count, embedding_model}'; }

# Process Elegant Weddings docs
for d in $EW_DEP $EW_CAN; do process "$EW" "$d"; done
# Process Royal Events docs
process "$RE" "$RE_REF"
# Expected: each -> status "processed", chunk_count >= 1
```

Inspect chunks for one document:

```bash
curl -s http://localhost:8000/api/documents/$EW_DEP/chunks \
  -H "Authorization: Bearer $EW" | jq '{total, first: .chunks[0] | {chunk_index, chunk_text}}'
# Expected: total >= 1, chunk_text contains the deposit policy text (no embedding vector in output)
```

---

## Step 4 + 5 — Query as Tenant 1 (Elegant Weddings); confirm T1-only sources

```bash
curl -s -X POST http://localhost:8000/api/rag/query \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"query":"Is the deposit refundable if I cancel?","top_k":4}' \
  | jq '{status, sources: [.sources[] | {document_title, document_type, score}]}'
```

**Expected** — only Elegant Weddings deposit/cancellation sources:
```json
{
  "status": "grounded",
  "sources": [
    { "document_title": "Deposit Policy",      "document_type": "deposit_policy",      "score": 0.81 },
    { "document_title": "Cancellation Policy",  "document_type": "cancellation_policy", "score": 0.67 }
  ]
}
```
No Royal Events document appears.

---

## Step 6 + 7 — Query as Tenant 2 (Royal Events Agency); confirm T2-only sources

```bash
curl -s -X POST http://localhost:8000/api/rag/query \
  -H "Authorization: Bearer $RE" -H "Content-Type: application/json" \
  -d '{"query":"Is the deposit refundable if I cancel?","top_k":4}' \
  | jq '{status, sources: [.sources[] | {document_title, document_type, score}]}'
```

**Expected** — only Royal Events refund policy:
```json
{
  "status": "grounded",
  "sources": [
    { "document_title": "Refund Policy", "document_type": "deposit_policy", "score": 0.79 }
  ]
}
```
No Elegant Weddings document appears. **The same question returns each tenant's own policy only.**

### Explicit cross-tenant proof

```bash
# Elegant Weddings tries to read a Royal Events document's chunks -> blocked
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/documents/$RE_REF/chunks -H "Authorization: Bearer $EW"
# Expected: 403 (CROSS_TENANT_FORBIDDEN)
```

---

## Step 8 + 9 — Ask an unsupported question; confirm refuse / no source

```bash
curl -s -X POST http://localhost:8000/api/rag/query \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"query":"What is the weather forecast for next Tuesday?","top_k":4}' \
  | jq '{status, sources}'
```

**Expected** — no relevant source; the system refuses (no fabrication):
```json
{ "status": "no_source", "sources": [] }
```

Empty-corpus case (a fresh tenant with no processed docs) returns:
```json
{ "status": "no_documents", "sources": [] }
```

---

## Link a Query to a Message and View on the Detail Page

```bash
# Inject a client message (Spec 003) and capture its id
MSG=$(curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"client_name":"Alice Johnson","body":"Is the deposit refundable if I cancel?"}' \
  | jq -r '.message_id // .latest_message_id // .id')

# Run RAG linked to that message
curl -s -X POST http://localhost:8000/api/rag/query \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d "{\"query\":\"Is the deposit refundable if I cancel?\",\"message_id\":\"$MSG\"}" | jq '.status'

# Fetch the message's stored RAG results
curl -s http://localhost:8000/api/messages/$MSG/rag-results \
  -H "Authorization: Bearer $EW" | jq '{status, sources: [.sources[].document_title]}'
# Expected: status "grounded", sources ["Deposit Policy","Cancellation Policy"]
```

Then open `http://localhost:5173/conversations/<conversation_id>` — the **Knowledge Sources** panel (replacing the Spec 005 placeholder) shows the retrieved Elegant Weddings sources with title, type, snippet, and score.

---

## Role + Tenant Checks

```bash
# Staff can query/view but cannot process
EW_STAFF=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)

curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/documents/$EW_DEP/process \
  -H "Authorization: Bearer $EW_STAFF"     # Expected: 403 (staff cannot process)

curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/rag/query \
  -H "Authorization: Bearer $EW_STAFF" -H "Content-Type: application/json" \
  -d '{"query":"deposit refund"}'          # Expected: 200 (staff can query)

# Platform Admin blocked everywhere
ADMIN=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' | jq -r .access_token)
curl -s -X POST http://localhost:8000/api/rag/query -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json" -d '{"query":"deposit"}' | jq .error_code
# Expected: "INSUFFICIENT_ROLE"
```

---

## Run Tests + Eval

```bash
cd backend
pytest tests/unit/test_chunker.py tests/unit/test_embedder.py tests/unit/test_retriever.py -v
pytest tests/integration/test_rag.py -v        # AC-01..AC-17 (tenancy, statuses, roles)
pytest tests/eval/test_rag_eval.py -v          # precision@k on demo corpus + refuse-path check
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/rag.py
│   ├── services/rag_service.py
│   ├── rag/{chunker.py, embedder.py, retriever.py}
│   ├── models/{document_chunk.py, rag.py}
│   └── schemas/rag.py
├── alembic/versions/00xx_create_rag_tables.py   # CREATE EXTENSION vector + 3 tables
└── tests/{unit/test_chunker.py, unit/test_embedder.py, unit/test_retriever.py,
          integration/test_rag.py, eval/test_rag_eval.py}

frontend/src/
├── api/rag.ts
├── types/rag.ts
└── components/rag/{KnowledgeSourcesPanel.tsx, SourceCard.tsx}
```
