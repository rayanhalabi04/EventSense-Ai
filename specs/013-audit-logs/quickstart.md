# Quickstart: Audit Logs

**Branch**: `013-audit-logs`

This guide shows a developer how to test the audit log manually using the demo tenants. As you drive the EventSense AI workflow, each meaningful action appends a tenant-scoped, append-only audit entry; a manager reviews them in the dashboard. Logs are strictly tenant-scoped and redacted.

Steps:
1. Create a simulator message → confirm the message audit log.
2. Run intent classification → confirm the classification audit log.
3. Run risk detection → confirm the risk audit log.
4. Generate RAG retrieval + a suggested reply → confirm the RAG/reply audit logs.
5. Create a task → confirm the task audit log.
6. Create and resolve an escalation → confirm the escalation audit logs.
7. Attempt cross-tenant access → confirm the security audit log.
8. Confirm Tenant 1 cannot view Tenant 2 audit logs.

---

## Prerequisites

- Specs 001–012 implemented and migrated (messages, intent, risk, documents, RAG, replies, tasks, escalations)
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`
- A staff and a manager account per tenant
- `AUDIT_STAFF_MESSAGE_VIEW_ENABLED=true` (for the optional staff message-scoped check)

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_audit_logs migration (append-only table + indexes).
# Recommended: confirm UPDATE/DELETE on audit_logs are revoked for the app DB role.
```

---

## Login + helpers

```bash
EW_STAFF=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
EW_MGR=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@elegant-weddings.demo","password":"manager-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
RE_STAFF=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)
RE_MGR=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@royal-events.demo","password":"manager-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)

inject () {  # $1=token $2=body -> echoes message id
  curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg b "$2" '{client_name:"Demo Client", body:$b}')" \
    | jq -r '.message_id // .latest_message_id // .id'
}

# List the manager's audit logs, optionally filtered. $1=token, rest=query string
audit () { curl -s "http://localhost:8000/api/audit-logs?$2" -H "Authorization: Bearer $1"; }
```

> The login itself should already have appended a `user_login` entry — you can confirm it later with `audit "$EW_MGR" "event_type=user_login"`.

---

## Step 1 — Create a simulator message → message audit log

```bash
M1=$(inject "$EW_STAFF" "Hi, can you send me your pricing for a 150-guest wedding?")

audit "$EW_MGR" "message_id=$M1&event_type=message_created_by_simulator" \
  | jq '.items[] | {event_type, actor_type, severity, entity_type, message_id}'
```
**Expected**: one entry, `event_type:"message_created_by_simulator"` (or `message_received`), `actor_type` `user`/`system`, `severity:"info"`, `entity_type:"message"`, `message_id` = `M1`.

---

## Step 2 — Intent classification → classification audit log

```bash
# (Classification runs in the pipeline on ingest, or trigger it per your 006 endpoint.)
audit "$EW_MGR" "message_id=$M1&event_type=intent_classified" \
  | jq '.items[] | {event_type, actor_type, severity, metadata}'
```
**Expected**: `event_type:"intent_classified"`, `actor_type:"ai_service"`, `severity:"info"`, and `metadata` containing `predicted_label` (e.g., `"pricing_request"`) + `confidence`. **No** prompt, model internals, or raw text.

---

## Step 3 — Risk detection → risk audit log

```bash
audit "$EW_MGR" "message_id=$M1&event_type=risk_detected" \
  | jq '.items[] | {event_type, actor_type, severity, metadata}'
```
**Expected**: `event_type:"risk_detected"`, `actor_type:"ai_service"`, `severity` `info`/`warning`, `metadata` with `risk_level` + a short `risk_reason`.

Trigger a high-risk message to see a warning-level risk + (later) a security flow:
```bash
M2=$(inject "$EW_STAFF" "I am furious and want to cancel; the wedding is next week!")
audit "$EW_MGR" "message_id=$M2&event_type=risk_detected" | jq '.items[0].metadata'
```

---

## Step 4 — RAG retrieval + suggested reply → RAG/reply audit logs

```bash
# A question that should retrieve a grounded source (assumes a pricing/policy doc is uploaded for 008/009)
M3=$(inject "$EW_STAFF" "Is the deposit refundable if we cancel 60 days before the event?")

audit "$EW_MGR" "message_id=$M3" \
  | jq '[.items[] | {event_type, actor_type, severity}]'
# Expected to include: rag_retrieved (or rag_no_source_found), suggested_reply_generated.

# Force a no-source case (a question unrelated to any uploaded doc):
M4=$(inject "$EW_STAFF" "Do you provide live elephants for the entrance?")
audit "$EW_MGR" "message_id=$M4&event_type=rag_no_source_found" \
  | jq '.items[] | {event_type, severity, metadata}'
# Expected: rag_no_source_found, severity "warning", metadata references the message,
#           and contains NO unsupported/fabricated answer text.
```
Now approve/reject a reply and confirm the lifecycle events:
```bash
# (Use your 010 endpoints to edit/approve/reject the generated reply for M3, then:)
audit "$EW_MGR" "message_id=$M3&event_type=suggested_reply_approved" \
  | jq '.items[] | {event_type, actor_type, actor_user_id}'
# Expected: actor_type "user", actor_user_id set (the staff who approved).
```

---

## Step 5 — Create a task → task audit log

```bash
# (Create a follow-up task for M2 via your 011 endpoint; capture its id if returned.)
audit "$EW_MGR" "event_type=task_created" \
  | jq '.items[0] | {event_type, actor_type, entity_type, metadata}'
# Expected: task_created, actor_type "user", entity_type "task", metadata.task_id present.
```

---

## Step 6 — Create and resolve an escalation → escalation audit logs

```bash
# Create an escalation for the high-risk message M2 (Spec 012)
E1=$(curl -s -X POST http://localhost:8000/api/escalations \
  -H "Authorization: Bearer $EW_STAFF" -H "Content-Type: application/json" \
  -d "$(jq -n --arg m "$M2" '{message_id:$m, priority:"high"}')" | jq -r '.id')

# Resolve it as a manager
curl -s -X POST http://localhost:8000/api/escalations/$E1/resolve \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"manager_notes":"Called the client; arranged a redo."}' > /dev/null

# Entity-scoped audit for the escalation
curl -s http://localhost:8000/api/escalations/$E1/audit-logs -H "Authorization: Bearer $EW_MGR" \
  | jq '[.items[] | {event_type, actor_type, severity}]'
# Expected: escalation_created (actor "user") and escalation_resolved (actor "user").
```

---

## Step 7 — Attempt cross-tenant access → security audit log

```bash
# Create an escalation in Royal Events
MR=$(inject "$RE_STAFF" "We must cancel, the venue flooded.")
ER=$(curl -s -X POST http://localhost:8000/api/escalations \
  -H "Authorization: Bearer $RE_STAFF" -H "Content-Type: application/json" \
  -d "$(jq -n --arg m "$MR" '{message_id:$m, priority:"urgent"}')" | jq -r '.id')

# Elegant Weddings manager attempts to read the Royal Events escalation -> blocked
curl -s -o /dev/null -w "blocked status: %{http_code}\n" \
  http://localhost:8000/api/escalations/$ER -H "Authorization: Bearer $EW_MGR"
# Expected: 403 (CROSS_TENANT_FORBIDDEN)

# A cross_tenant_access_blocked entry is recorded IN THE ATTEMPTING TENANT (Elegant Weddings)
audit "$EW_MGR" "event_type=cross_tenant_access_blocked&severity=security" \
  | jq '.items[0] | {event_type, severity, actor_type, actor_user_id, metadata}'
# Expected: severity "security", actor_type "user", actor_user_id = the EW manager,
#           metadata references the attempt (attempted_route / attempted_entity_type)
#           and contains NO Royal Events data (no ER fields, no RE tenant id).
```

---

## Step 8 — Tenant isolation (Tenant 1 cannot view Tenant 2 audit logs)

```bash
# Royal Events generated its own entries (MR ingest, classification, escalation, etc.)
# Confirm the Elegant Weddings manager cannot see ANY Royal Events entry.

# The RE escalation id ER must not appear in EW's logs:
audit "$EW_MGR" "" | jq "[.items[].entity_id] | index(\"$ER\")"
# Expected: null

# The RE message MR must not appear in EW's logs:
audit "$EW_MGR" "message_id=$MR" | jq '.total'
# Expected: 0  (EW cannot query RE's message audit)

# Conversely, the RE manager sees RE entries but none of EW's:
audit "$RE_MGR" "message_id=$M1" | jq '.total'
# Expected: 0  (M1 belongs to Elegant Weddings)
```

---

## Role + Redaction + Best-Effort Checks

```bash
# Staff cannot read the tenant-wide list
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/audit-logs \
  -H "Authorization: Bearer $EW_STAFF"
# Expected: 403 (INSUFFICIENT_ROLE)

# Staff CAN read a message-scoped view (when enabled), with security entries excluded
curl -s http://localhost:8000/api/messages/$M1/audit-logs -H "Authorization: Bearer $EW_STAFF" \
  | jq '[.items[].severity] | unique'
# Expected: no "security" values present

# Platform Admin blocked
ADMIN=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' | jq -r .access_token)
curl -s http://localhost:8000/api/audit-logs -H "Authorization: Bearer $ADMIN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE"

# Redaction: no entry leaks secrets/prompts/tokens/keys
audit "$EW_MGR" "" | jq '
  [.items[].redacted_summary // "" | ascii_downcase]
  | map(select(test("password|secret|token|api[_ ]?key|prompt|bearer ")))
  | length'
# Expected: 0

# Append-only: there is no update/delete route
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
  http://localhost:8000/api/audit-logs/$(audit "$EW_MGR" "" | jq -r '.items[0].id') \
  -H "Authorization: Bearer $EW_MGR"
# Expected: 405 (METHOD_NOT_ALLOWED — no such route)
```

**Best-effort (white-box check)**: temporarily force `AuditService.log_event` to raise (e.g., point it at an invalid table in a test config), then drive a classification — the classification must still succeed and return normally; only an application-log warning + a metric increment should appear. The primary workflow is never broken by a logging failure.

---

## See It in the UI

1. Open `http://localhost:5173/audit-logs` as a **manager** — the dashboard lists the tenant's entries newest-first with columns (time, event, actor [name / "System" / "AI service"], severity badge, related entity, redacted summary). Filter by event type, actor, date range, entity, and severity. Open an entry to see its full redacted metadata + references. There are **no** edit/delete controls.
2. Filter `severity = security` — see `cross_tenant_access_blocked` and any `guardrail_refusal` entries; confirm none expose another tenant's data.
3. Open a message at `http://localhost:5173/conversations/<conversation_id>` — the optional **Activity** panel shows that message's audit entries (as a **staff** user, security entries are hidden).
4. As a **staff** user, `/audit-logs` (tenant-wide) is not accessible (hidden/forbidden); only the message-scoped Activity panel is available.

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_audit_redaction.py tests/unit/test_audit_service.py -v
pytest tests/integration/test_audit_logs.py -v   # AC-01..AC-18 (writes, append-only, tenancy, redaction, best-effort)
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/audit_logs.py
│   ├── services/audit_service.py        # log_event (best-effort) + reads
│   ├── services/audit_redaction.py      # redact()
│   ├── models/audit_log.py
│   └── schemas/audit.py
├── alembic/versions/00xx_create_audit_logs.py
└── tests/{unit/test_audit_service.py, unit/test_audit_redaction.py, integration/test_audit_logs.py}

frontend/src/
├── api/auditLogs.ts
├── types/audit.ts
├── pages/AuditLogsPage.tsx
└── components/audit/{AuditLogTable.tsx, AuditLogRow.tsx, AuditLogDetail.tsx, AuditLogFilters.tsx}
```
