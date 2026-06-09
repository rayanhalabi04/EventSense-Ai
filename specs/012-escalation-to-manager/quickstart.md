# Quickstart: Escalation to Manager

**Branch**: `012-escalation-to-manager`

This guide shows a developer how to test escalations manually across five scenarios using the demo tenants. Escalations capture the AI context (intent/risk/RAG/reply) and route the case to a manager. They are strictly tenant-scoped.

Scenarios:
1. High-risk complaint → escalate.
2. Cancellation request → escalate before replying.
3. Payment issue → escalate (or task).
4. Manager review flow (in_review → notes → resolve).
5. Tenant isolation — Tenant 1 cannot access Tenant 2 escalations.

---

## Prerequisites

- Specs 001–011 implemented and migrated (messages, intent, risk; optionally RAG + suggested replies for richer context)
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`
- A staff and a manager account per tenant

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_escalations migration (and allows messages.status = escalated)
```

---

## Login + helpers

```bash
EW_STAFF=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
EW_MGR=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@elegant-weddings.demo","password":"manager-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
RE_MGR=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@royal-events.demo","password":"manager-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)

inject () {  # $1=token $2=body -> echoes message id
  curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg b "$2" '{client_name:"Demo Client", body:$b}')" \
    | jq -r '.message_id // .latest_message_id // .id'
}

escalate () {  # $1=token $2=message_id $3=priority -> echoes escalation json
  curl -s -X POST http://localhost:8000/api/escalations \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg m "$2" --arg p "$3" '{message_id:$m, priority:$p}')"
}
```

---

## Scenario 1 — High-risk complaint → escalate

```bash
M1=$(inject "$EW_STAFF" "I am very unhappy with the decoration sample and the wedding is next week.")

escalate "$EW_STAFF" "$M1" "high" \
  | jq '{id, status, priority, intent_label, risk_level, risk_reason, suggested_reply_id, message_id}'
```
**Expected**: `status:"open"`, `priority:"high"`, `intent_label:"complaint"`, `risk_level:"high"`, a `risk_reason`, captured `suggested_reply_id` if a reply exists, linked to `M1`.

Confirm the message was marked + appears for the message:
```bash
curl -s http://localhost:8000/api/messages/$M1/escalations -H "Authorization: Bearer $EW_STAFF" \
  | jq '{total, statuses: [.items[].status]}'
# Expected: total 1, ["open"]
```

---

## Scenario 2 — Cancellation request → escalate before replying

```bash
M2=$(inject "$EW_STAFF" "I want to cancel the booking. Is the deposit refundable?")

escalate "$EW_STAFF" "$M2" "high" \
  | jq '{intent_label, risk_level, suggested_reply_id, source_document_ids}'
# Expected: intent "cancellation_request", risk "high",
#           suggested_reply_id present if a reply was generated,
#           source ids present if RAG retrieved the cancellation/deposit policy.
```
The captured `suggested_reply_id` links the draft — but escalation does **not** approve/send it; the reply stays in its own (un-approved) state.

---

## Scenario 3 — Payment issue → escalate (or task)

```bash
M3=$(inject "$EW_STAFF" "I paid the deposit but no one confirmed.")

E3=$(escalate "$EW_STAFF" "$M3" "medium" | jq -r '.id')
echo "escalation: $E3"
# Expected: a medium/high escalation; intent "payment_issue".
# (Staff could instead create a task via Spec 011 — this feature does not create tasks.)
```

---

## Scenario 4 — Manager review flow

```bash
# Manager lists the queue (urgent/open first)
curl -s http://localhost:8000/api/escalations -H "Authorization: Bearer $EW_MGR" \
  | jq '[.items[] | {id, priority, status, intent_label}]'

# Open the complaint escalation, move to in_review + assign to self
E1=$(curl -s "http://localhost:8000/api/escalations?status=open" -H "Authorization: Bearer $EW_MGR" \
  | jq -r '.items[0].id')

curl -s -X PATCH http://localhost:8000/api/escalations/$E1 \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"status":"in_review","manager_notes":"Calling the client now."}' \
  | jq '{status, manager_notes}'
# Expected: status "in_review", note stored

# Resolve it
curl -s -X POST http://localhost:8000/api/escalations/$E1/resolve \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"manager_notes":"Arranged a redo of the decoration; client satisfied."}' \
  | jq '{status, resolved_at}'
# Expected: status "resolved", resolved_at set

# Resolving again is rejected (terminal)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/escalations/$E1/resolve \
  -H "Authorization: Bearer $EW_MGR"
# Expected: 422 (INVALID_STATE_TRANSITION)
```

Staff cannot resolve:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/escalations/$E3/resolve \
  -H "Authorization: Bearer $EW_STAFF"
# Expected: 403 (INSUFFICIENT_ROLE)
```

---

## Scenario 5 — Tenant isolation (Tenant 1 cannot access Tenant 2 escalations)

```bash
# Create an escalation in Royal Events
RE_STAFF=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)
MR=$(inject "$RE_STAFF" "We must cancel, the venue flooded.")
ER=$(escalate "$RE_STAFF" "$MR" "urgent" | jq -r '.id')

# Elegant Weddings manager lists queue -> Royal Events escalation absent
curl -s http://localhost:8000/api/escalations -H "Authorization: Bearer $EW_MGR" \
  | jq "[.items[].id] | index(\"$ER\")"
# Expected: null (not present)

# Elegant Weddings manager tries to read the Royal Events escalation -> blocked
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/escalations/$ER \
  -H "Authorization: Bearer $EW_MGR"
# Expected: 403

curl -s http://localhost:8000/api/escalations/$ER -H "Authorization: Bearer $EW_MGR" | jq .error_code
# Expected: "CROSS_TENANT_FORBIDDEN"
```

Cross-tenant assignee is rejected:
```bash
# Assign a Royal Events manager to an Elegant Weddings escalation
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH http://localhost:8000/api/escalations/$E3 \
  -H "Authorization: Bearer $EW_MGR" -H "Content-Type: application/json" \
  -d '{"assigned_manager_id":"<a royal-events manager id>"}'
# Expected: 422 (INVALID_ASSIGNEE)
```

---

## Role + No-Side-Effect Checks

```bash
# Platform Admin blocked
ADMIN=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' | jq -r .access_token)
curl -s http://localhost:8000/api/escalations -H "Authorization: Bearer $ADMIN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE"

# Non-existent related message -> 404
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/escalations \
  -H "Authorization: Bearer $EW_STAFF" -H "Content-Type: application/json" \
  -d '{"message_id":"00000000-0000-0000-0000-000000000000","priority":"high"}'
# Expected: 404
```
Creating/resolving an escalation sends **no** client message, does **not** approve/send the suggested reply, and creates **no** task — verify no such effects occur.

---

## See It in the UI

1. Open a high-risk message at `http://localhost:5173/conversations/<conversation_id>` — an **escalation recommendation** banner appears (from Spec 007). The **Escalate** control (replacing the Spec 005 placeholder) opens a form pre-filled with priority from risk; confirm to create.
2. Open `http://localhost:5173/escalations` as a **manager** — the queue lists the tenant's escalations (urgent/open first) with priority/status/intent/risk badges and the related message link. Filter by status/priority/assignee.
3. Open an escalation → see the full captured context (message, intent, risk + reason, AI summary, RAG sources, linked suggested reply). Move to in_review, add notes, assign, resolve or cancel. Terminal escalations are read-only.
4. As a **staff** user, the queue is viewable but resolve/assign controls are hidden/disabled (read + create only).

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_escalation_service.py tests/unit/test_escalation_summarizer.py -v
pytest tests/integration/test_escalations.py -v   # AC-01..AC-18 (snapshot, tenancy, role split, transitions, no side effects)
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/escalations.py
│   ├── services/escalation_service.py
│   ├── ai/escalation_summarizer.py     # optional
│   ├── models/escalation.py
│   └── schemas/escalation.py
├── alembic/versions/00xx_create_escalations.py
└── tests/{unit/test_escalation_service.py, unit/test_escalation_summarizer.py, integration/test_escalations.py}

frontend/src/
├── api/escalations.ts
├── types/escalation.ts
├── pages/EscalationsPage.tsx
└── components/escalations/{EscalationList.tsx, EscalationRow.tsx, EscalationDetail.tsx}
```
