# Quickstart: Risk Detection

**Branch**: `007-risk-detection`

This guide shows a developer how to test risk detection locally using the five demo messages. Risk runs **after** intent classification (Spec 006), so each injected message is first classified, then assessed.

---

## Prerequisites

- Specs 001–006 fully implemented and migrated (intent classification must be working)
- Backend running on `http://localhost:8000`, frontend on `http://localhost:5173`
- `RISK_RULES_VERSION` set (default `rules-v1`)

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_risk_assessments migration
```

---

## Login

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)
```

---

## Helper: inject a message and read its risk

```bash
inject_and_assess () {
  local body="$1"
  local mid
  mid=$(curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"client_name\":\"Demo Client\",\"body\":$(jq -Rn --arg b "$body" '$b')}" \
    | jq -r '.message_id // .latest_message_id // .id')
  # Auto-classify + auto-assess happen on creation; read the risk:
  echo ">> $body"
  curl -s http://localhost:8000/api/messages/$mid/risk-assessment \
    -H "Authorization: Bearer $TOKEN" | jq '{level, flag, escalation_recommended, reason}'
  echo
}
```

---

## Demo Message 1 — pricing (expected: low)

```bash
inject_and_assess "Can you send me your wedding package prices?"
```
**Expected**:
```json
{ "level": "low", "flag": null, "escalation_recommended": false, "reason": "Routine pricing request." }
```

---

## Demo Message 2 — guest count change (expected: high, large delta)

```bash
inject_and_assess "We need to change the guest count from 150 to 220."
```
**Expected** (delta of 70 ≥ threshold → raised to high):
```json
{ "level": "high", "flag": "guest_count_change", "escalation_recommended": true, "reason": "Guest count change of 70 (150→220)." }
```

> A smaller change (e.g., "can we add one more guest?") should yield `medium`.

---

## Demo Message 3 — cancellation + refund (expected: high)

```bash
inject_and_assess "I want to cancel the booking. Is the deposit refundable?"
```
**Expected**:
```json
{ "level": "high", "flag": "cancellation_risk", "escalation_recommended": true, "reason": "Cancellation intent with deposit/refund mention." }
```

---

## Demo Message 4 — payment not confirmed (expected: medium→high)

```bash
inject_and_assess "I paid the deposit but no one confirmed."
```
**Expected** ("paid but unconfirmed" raises payment risk):
```json
{ "level": "high", "flag": "payment_risk", "escalation_recommended": true, "reason": "Payment made but not confirmed." }
```

> A neutral payment question ("what payment methods do you accept?") should yield `medium`.

---

## Demo Message 5 — complaint + urgency (expected: high)

```bash
inject_and_assess "I am very unhappy with the decoration sample and the wedding is next week."
```
**Expected** (complaint baseline high; "next week" reinforces urgency):
```json
{ "level": "high", "flag": "complaint", "escalation_recommended": true, "reason": "Complaint with urgency: event is next week." }
```

---

## Manual Re-Assessment

```bash
MID=<paste a message id>
curl -s -X POST http://localhost:8000/api/messages/$MID/risk-assessment \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"force": false}' | jq '{level, flag, status}'
# Re-runs rules; overwrites the rule-generated result (status stays assessed)
```

### Assess before classification → 409

```bash
# If a message somehow has no classification yet:
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8000/api/messages/$UNCLASSIFIED_ID/risk-assessment \
  -H "Authorization: Bearer $TOKEN"
# Expected: 409 (NOT_CLASSIFIED)
```

---

## Human Review

```bash
curl -s -X PATCH http://localhost:8000/api/messages/$MID/risk-assessment/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"level":"high","flag":"complaint","reason":"Confirmed complaint; client upset about decoration."}' \
  | jq '{level, flag, status, reviewed_by, reviewed_at}'
# Expected: status="reviewed", reviewer + timestamp set
```

### Invalid level/flag is rejected

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH \
  http://localhost:8000/api/messages/$MID/risk-assessment/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"level":"critical","flag":"complaint","reason":"x"}'
# Expected: 422  ("critical" is not a valid RiskLevel)
```

### Reviewed assessment is protected from auto-overwrite

```bash
curl -s -X POST http://localhost:8000/api/messages/$MID/risk-assessment \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"force": false}' | jq '{level, status}'
# Expected: status still "reviewed"; level unchanged
```

---

## Tenant Isolation

```bash
ROYAL_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' \
  | jq -r .access_token)

curl -s http://localhost:8000/api/messages/$MID/risk-assessment \
  -H "Authorization: Bearer $ROYAL_TOKEN" | jq '.error_code'
# Expected: "CROSS_TENANT_FORBIDDEN" (403)
```

---

## Platform Admin Blocked

```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' \
  | jq -r .access_token)

curl -s http://localhost:8000/api/messages/$MID/risk-assessment \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.error_code'
# Expected: "INSUFFICIENT_ROLE" (403)
```

---

## See It in the UI

1. Open the inbox at `http://localhost:5173/inbox` — each message shows a colour-coded risk badge (low=muted, medium=amber, high=red) next to the Spec 006 intent badge; high-risk rows are emphasised.
2. Click into a conversation — the detail page's **Risk / Sentiment** panel now shows level + primary flag + reason + an "escalation recommended" indicator (replacing the Spec 005 placeholder). The remaining placeholders stay "coming soon".
3. Use the risk review control on a message to correct level/flag/reason; the badge/panel update and the status becomes "reviewed".

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_risk_engine.py -v        # rule logic in isolation
pytest tests/integration/test_risk.py -v        # endpoints, tenancy, review (AC-01..AC-18)
# Expected: all tests pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/risk.py
│   ├── services/risk_service.py
│   ├── risk/{engine.py, rules.py}
│   ├── models/risk.py
│   └── schemas/risk.py
├── alembic/versions/00xx_create_risk_assessments.py
└── tests/{unit/test_risk_engine.py, integration/test_risk.py}

frontend/src/
├── api/risk.ts
├── types/risk.ts
└── components/risk/{RiskBadge.tsx, RiskPanel.tsx, RiskReviewControl.tsx}
```
