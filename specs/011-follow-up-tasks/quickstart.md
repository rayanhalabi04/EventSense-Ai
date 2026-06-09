# Quickstart: Follow-Up Tasks

**Branch**: `011-follow-up-tasks`

This guide shows a developer how to test follow-up tasks manually across five scenarios using the demo tenants. Tasks are created from messages and are strictly tenant-scoped.

Scenarios:
1. Guest count change message → task.
2. Payment confirmation issue → task.
3. Client callback request → task.
4. Tenant isolation — Tenant 1 cannot access Tenant 2 tasks.
5. Task completion.

---

## Prerequisites

- Specs 001–010 implemented and migrated (tenants, auth, messages; optionally intent/risk/reply for AI suggestions)
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_tasks migration (and allows messages.status = task_created)
```

---

## Login + helpers

```bash
EW=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
RE=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)

inject () {  # $1=token $2=body -> echoes message id
  curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg b "$2" '{client_name:"Demo Client", body:$b}')" \
    | jq -r '.message_id // .latest_message_id // .id'
}

create_task () {  # $1=token $2=message_id $3=title $4=description $5=priority -> echoes task json
  curl -s -X POST http://localhost:8000/api/tasks \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg m "$2" --arg t "$3" --arg d "$4" --arg p "$5" \
          '{related_message_id:$m, title:$t, description:$d, priority:$p}')"
}
```

---

## Scenario 1 — Guest count change → task

```bash
M1=$(inject "$EW" "We need to change the guest count from 150 to 220.")

create_task "$EW" "$M1" \
  "Check catering capacity for updated guest count" \
  "Confirm whether catering, seating, and venue setup can support 220 guests." \
  "high" | jq '{id, title, priority, status, related_message_id}'
```
**Expected**: a task with `status:"open"`, `priority:"high"`, linked to `M1`.

Confirm the message was marked:
```bash
curl -s http://localhost:8000/api/messages/$M1/tasks -H "Authorization: Bearer $EW" \
  | jq '{total, titles: [.items[].title]}'
# Expected: total 1, ["Check catering capacity for updated guest count"]
```

### Optional: AI suggestion first (creates nothing)

```bash
curl -s -X POST http://localhost:8000/api/messages/$M1/task-suggestion \
  -H "Authorization: Bearer $EW" | jq '{title, priority, source}'
# Expected: a proposed title + priority, source "ai_suggestion"; NO task created by this call.
```

---

## Scenario 2 — Payment confirmation issue → task

```bash
M2=$(inject "$EW" "I paid the deposit but no one confirmed.")

create_task "$EW" "$M2" \
  "Verify deposit payment confirmation" \
  "Check payment records and confirm the deposit status with the client." \
  "high" | jq '{title, priority, status}'
# Expected: status "open", priority "high"
```

---

## Scenario 3 — Client callback request → task

```bash
M3=$(inject "$EW" "Can someone call me today?")

T3=$(create_task "$EW" "$M3" \
  "Call client today" \
  "Contact client regarding their request." \
  "medium" | jq -r '.id')
echo "task: $T3"
# Expected: a medium-priority "Call client today" task
```

---

## Scenario 4 — Tenant isolation (Tenant 1 cannot access Tenant 2 tasks)

```bash
# Create a task in Royal Events
MR=$(inject "$RE" "Please confirm the band timing.")
TR=$(create_task "$RE" "$MR" "Confirm band timing" "Check with the band." "medium" | jq -r '.id')

# Elegant Weddings lists tasks -> should NOT include the Royal Events task
curl -s http://localhost:8000/api/tasks -H "Authorization: Bearer $EW" \
  | jq '[.items[].title]'
# Expected: only Elegant Weddings task titles; "Confirm band timing" absent

# Elegant Weddings tries to read the Royal Events task by id -> blocked
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/tasks/$TR \
  -H "Authorization: Bearer $EW"
# Expected: 403

curl -s http://localhost:8000/api/tasks/$TR -H "Authorization: Bearer $EW" | jq .error_code
# Expected: "CROSS_TENANT_FORBIDDEN"
```

Cross-tenant assignee is also rejected:
```bash
# Try to create an EW task assigned to a Royal Events user id
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d "{\"related_message_id\":\"$M1\",\"title\":\"x\",\"assigned_to\":\"<a royal-events user id>\"}"
# Expected: 422 (INVALID_ASSIGNEE)
```

---

## Scenario 5 — Task completion

```bash
# Progress then complete the callback task from Scenario 3
curl -s -X PATCH http://localhost:8000/api/tasks/$T3 \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"status":"in_progress"}' | jq '.status'
# Expected: "in_progress"

curl -s -X POST http://localhost:8000/api/tasks/$T3/complete \
  -H "Authorization: Bearer $EW" | jq '{status, completed_at}'
# Expected: status "completed", completed_at set

# Completing again is rejected (terminal)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/tasks/$T3/complete \
  -H "Authorization: Bearer $EW"
# Expected: 422 (INVALID_STATE_TRANSITION)

# Completed task still appears when filtering by status
curl -s "http://localhost:8000/api/tasks?status=completed" -H "Authorization: Bearer $EW" \
  | jq '[.items[].title]'
# Expected: includes "Call client today"
```

Cancel path:
```bash
M4=$(inject "$EW" "Never mind, sorted it myself.")
T4=$(create_task "$EW" "$M4" "Follow up (maybe)" "" "low" | jq -r '.id')
curl -s -X PATCH http://localhost:8000/api/tasks/$T4 \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"status":"cancelled"}' | jq '.status'
# Expected: "cancelled"
```

---

## Role + No-Side-Effect Checks

```bash
# Platform Admin blocked
ADMIN=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' | jq -r .access_token)
curl -s http://localhost:8000/api/tasks -H "Authorization: Bearer $ADMIN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE"

# Missing title -> 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d "{\"related_message_id\":\"$M1\",\"title\":\"   \"}"
# Expected: 422

# Non-existent related message -> 404
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"related_message_id":"00000000-0000-0000-0000-000000000000","title":"x"}'
# Expected: 404
```
Creating a task sends **no** client message and creates **no** escalation — verify no such records/effects appear.

---

## See It in the UI

1. Open a conversation at `http://localhost:5173/conversations/<conversation_id>`.
2. The **Create Task** control (replacing the Spec 005 placeholder) opens a form prefilled from the message (optionally "Suggest with AI"). Edit and confirm to create.
3. Open `http://localhost:5173/tasks` — the Tasks page lists the tenant's tasks with status/priority badges, assignee, due date (overdue highlighted), and the related message link. Filter by status/priority/assignee.
4. Open a task → change assignee (manager), progress to in_progress, complete or cancel. Terminal tasks are read-only.

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_task_service.py tests/unit/test_task_suggester.py -v
pytest tests/integration/test_tasks.py -v     # AC-01..AC-18 (CRUD, tenancy, transitions, no side effects)
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/tasks.py
│   ├── services/task_service.py
│   ├── ai/task_suggester.py            # optional
│   ├── models/task.py
│   └── schemas/task.py
├── alembic/versions/00xx_create_tasks.py
└── tests/{unit/test_task_service.py, unit/test_task_suggester.py, integration/test_tasks.py}

frontend/src/
├── api/tasks.ts
├── types/task.ts
├── pages/TasksPage.tsx
└── components/tasks/{TaskList.tsx, TaskRow.tsx, TaskForm.tsx, TaskDetail.tsx}
```
