# Quickstart: Document Upload

**Branch**: `008-document-upload`

This guide shows a developer how to test tenant-scoped document management locally using the two demo tenants — **Elegant Weddings** and **Royal Events Agency** — and to prove that one tenant can never see the other's documents.

---

## Prerequisites

- Specs 001–002 fully implemented and migrated (tenants + auth + roles)
- Backend running on `http://localhost:8000`, frontend on `http://localhost:5173`
- Demo manager and staff accounts for both tenants

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_documents migration
```

---

## Login (managers of both tenants)

```bash
EW_MGR=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"manager@elegant-weddings.demo","password":"manager-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

RE_MGR=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"manager@royal-events.demo","password":"manager-password-2","tenant_slug":"royal-events-agency"}' \
  | jq -r .access_token)
```

---

## Helper: create a document (JSON content path)

```bash
create_doc () {  # $1=token  $2=title  $3=type  $4=content
  curl -s -X POST http://localhost:8000/api/documents \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg t "$2" --arg ty "$3" --arg c "$4" \
          '{title:$t, document_type:$ty, content:$c}')" \
    | jq '{id, title, document_type, status, enabled}'
}
```

---

## Seed Elegant Weddings documents

```bash
create_doc "$EW_MGR" "Premium Wedding Package" "wedding_packages" \
  "Premium package: full-day coordination, 200 guests, premium florals, 3-course plated dinner."
create_doc "$EW_MGR" "Deposit Policy" "deposit_policy" \
  "A 30% deposit confirms the booking. Deposits are non-refundable within 45 days of the event."
create_doc "$EW_MGR" "Cancellation Policy" "cancellation_policy" \
  "Cancellations 90+ days before the event receive a 50% refund of payments beyond the deposit."
create_doc "$EW_MGR" "Decoration Rules" "decoration_rules" \
  "Open flames are not permitted indoors. All decor must be removed by midnight on the event day."
```

---

## Seed Royal Events Agency documents

```bash
create_doc "$RE_MGR" "Luxury Wedding Package" "wedding_packages" \
  "Luxury package: two-day event, 350 guests, designer florals, live band, premium bar."
create_doc "$RE_MGR" "Refund Policy" "deposit_policy" \
  "Deposits are 25% and fully refundable up to 60 days before the event."
create_doc "$RE_MGR" "Catering Policy" "catering_rules" \
  "External caterers must be licensed and approved 30 days in advance. Corkage applies to outside beverages."
create_doc "$RE_MGR" "Bridal Entrance Setup Policy" "decoration_rules" \
  "Bridal entrance requires a 6-meter aisle clearance and approved lighting rigging."
```

---

## List documents per tenant (tenant isolation)

```bash
echo "Elegant Weddings:"; curl -s http://localhost:8000/api/documents \
  -H "Authorization: Bearer $EW_MGR" | jq '[.items[].title]'
# Expected: ["Decoration Rules","Cancellation Policy","Deposit Policy","Premium Wedding Package"] (order by updated_at desc)

echo "Royal Events Agency:"; curl -s http://localhost:8000/api/documents \
  -H "Authorization: Bearer $RE_MGR" | jq '[.items[].title]'
# Expected: ["Bridal Entrance Setup Policy","Catering Policy","Refund Policy","Luxury Wedding Package"]
```

Each tenant sees **only its own** four documents — no overlap.

---

## Cross-tenant access is blocked

```bash
# Capture an Elegant Weddings document id
EW_DOC=$(curl -s http://localhost:8000/api/documents \
  -H "Authorization: Bearer $EW_MGR" | jq -r '.items[0].id')

# Royal Events manager tries to read it
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/documents/$EW_DOC \
  -H "Authorization: Bearer $RE_MGR"
# Expected: 403

curl -s http://localhost:8000/api/documents/$EW_DOC \
  -H "Authorization: Bearer $RE_MGR" | jq .error_code
# Expected: "CROSS_TENANT_FORBIDDEN"
```

---

## Filter by type and status

```bash
curl -s "http://localhost:8000/api/documents?document_type=wedding_packages" \
  -H "Authorization: Bearer $EW_MGR" | jq '[.items[].title]'
# Expected: ["Premium Wedding Package"]

curl -s "http://localhost:8000/api/documents?status=uploaded" \
  -H "Authorization: Bearer $EW_MGR" | jq '.total'
# Expected: 4 (all start as uploaded)
```

---

## Upload via file (multipart)

```bash
printf "FAQ\nQ: Do you offer payment plans?\nA: Yes, in three installments.\n" > /tmp/faq.md

curl -s -X POST http://localhost:8000/api/documents \
  -H "Authorization: Bearer $EW_MGR" \
  -F "title=Payment FAQ" -F "document_type=faq" -F "file=@/tmp/faq.md;type=text/markdown" \
  | jq '{title, document_type, status, source_filename, source_mime, content_bytes}'
# Expected: status "uploaded", source_filename "faq.md", source_mime "text/markdown"
```

### Unsupported file type is rejected

```bash
printf '{}' > /tmp/bad.json
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/documents \
  -H "Authorization: Bearer $EW_MGR" \
  -F "title=Bad" -F "document_type=other" -F "file=@/tmp/bad.json;type=application/json"
# Expected: 422 (UNSUPPORTED_FILE_TYPE)
```

---

## Edit content resets status to uploaded

```bash
DOC=$(curl -s http://localhost:8000/api/documents?document_type=deposit_policy \
  -H "Authorization: Bearer $EW_MGR" | jq -r '.items[0].id')

# Mark it processing_pending first
curl -s -X PATCH http://localhost:8000/api/documents/$DOC \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"status":"processing_pending"}' | jq '.status'
# Expected: "processing_pending"

# Now edit content -> status resets
curl -s -X PATCH http://localhost:8000/api/documents/$DOC \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"content":"A 35% deposit now confirms the booking."}' | jq '{status, content_bytes}'
# Expected: status "uploaded" (content change invalidates future RAG processing)
```

### Manager cannot set processed/failed

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH http://localhost:8000/api/documents/$DOC \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"status":"processed"}'
# Expected: 422 (STATUS_NOT_SETTABLE — owned by the future RAG feature)
```

---

## Disable vs delete

```bash
# Disable (reversible; stays listed)
curl -s -X PATCH http://localhost:8000/api/documents/$DOC \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"enabled":false}' | jq '.enabled'
# Expected: false

# Delete (permanent)
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://localhost:8000/api/documents/$DOC \
  -H "Authorization: Bearer $EW_MGR"
# Expected: 204

curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/documents/$DOC \
  -H "Authorization: Bearer $EW_MGR"
# Expected: 404
```

---

## Staff is read-only

```bash
EW_STAFF=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

# Staff can list/view
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/documents \
  -H "Authorization: Bearer $EW_STAFF"
# Expected: 200

# Staff cannot create
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/documents \
  -H "Authorization: Bearer $EW_STAFF" -H "Content-Type: application/json" \
  -d '{"title":"Nope","document_type":"faq","content":"x"}'
# Expected: 403 (INSUFFICIENT_ROLE)
```

---

## Platform Admin blocked

```bash
ADMIN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' \
  | jq -r .access_token)

curl -s http://localhost:8000/api/documents \
  -H "Authorization: Bearer $ADMIN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE" (403)
```

---

## See It in the UI

1. Open `http://localhost:5173/documents` as an Elegant Weddings **manager** — see the four seeded documents with type/status badges and create/upload controls.
2. Create a document (paste content) and upload one (`.md` file); both appear with status `uploaded`.
3. Edit a document's content — status badge returns to `uploaded`; disable one — it stays listed but marked disabled; delete one — it disappears.
4. Log in as an Elegant Weddings **staff** user — the list is visible but the create/edit/delete controls are hidden/disabled (read-only).
5. Log in as a **Royal Events** manager — only Royal Events documents are shown; Elegant Weddings documents are never visible.

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_file_extract.py -v        # MIME/size/extraction validation
pytest tests/integration/test_documents.py -v    # CRUD, tenancy, roles (AC-01..AC-17)
# Expected: all tests pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/documents.py
│   ├── services/document_service.py
│   ├── files/extract.py
│   ├── models/document.py
│   └── schemas/document.py
├── alembic/versions/00xx_create_documents.py
└── tests/{unit/test_file_extract.py, integration/test_documents.py}

frontend/src/
├── api/documents.ts
├── types/document.ts
├── pages/DocumentsPage.tsx
└── components/documents/{DocumentList.tsx, DocumentRow.tsx, DocumentForm.tsx, DocumentDetail.tsx}
```
