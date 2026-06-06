# Quickstart: Intent Classifier

**Branch**: `006-intent-classifier`

This guide shows a developer how to test intent classification locally using demo messages.

---

## Prerequisites

- Specs 001–005 fully implemented and migrated
- Backend running on `http://localhost:8000`, frontend on `http://localhost:5173`
- The intent model artifact present at `INTENT_MODEL_PATH` (see "Build the Demo Model" below)
- `INTENT_CONFIDENCE_THRESHOLD` set (default `0.45`)

---

## Build the Demo Model (one-time)

If no artifact exists yet, build the small demo model so the classifier is available:

```bash
cd backend
python -m app.ml.train_demo
# Writes vectorizer.joblib, model.joblib, labels.json, meta.json to backend/models/intent/
# meta.json model_version should read "tfidf-logreg-v1"
```

Confirm the backend logs `intent model loaded: tfidf-logreg-v1` on startup. If the artifact is missing, the app still starts but auto-classification is skipped and `POST /classify` returns 503.

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_classification_results migration
```

---

## Seed and Auto-Classify a Message

```bash
# Login as Elegant Weddings staff
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

# Inject a clearly pricing-related message (auto-classified on creation)
MSG_ID=$(curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"client_name":"Alice Johnson","body":"How much does your gold wedding package cost?"}' \
  | jq -r '.message_id // .latest_message_id // .id')

echo "Message: $MSG_ID"
```

---

## Read the Classification

```bash
curl -s http://localhost:8000/api/messages/$MSG_ID/classification \
  -H "Authorization: Bearer $TOKEN" | jq '{label, confidence, status, model_version}'
```

**Expected** (label depends on the demo model, pricing wording should score high):
```json
{ "label": "pricing_request", "confidence": 0.82, "status": "classified", "model_version": "tfidf-logreg-v1" }
```

---

## Trigger Manual (Re-)Classification

```bash
curl -s -X POST http://localhost:8000/api/messages/$MSG_ID/classify \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"force": false}' | jq '{label, confidence, status}'
# Expected: same label; re-running overwrites the model result (status stays classified)
```

---

## See a Low-Confidence / Needs-Review Case

```bash
# Ambiguous / off-topic text should fall below threshold -> other / needs_review
AMBIG_ID=$(curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"client_name":"Bob Smith","body":"ok 👍"}' \
  | jq -r '.message_id // .latest_message_id // .id')

curl -s http://localhost:8000/api/messages/$AMBIG_ID/classification \
  -H "Authorization: Bearer $TOKEN" | jq '{label, confidence, status}'
# Expected: { "label": "other", "confidence": <below 0.45>, "status": "needs_review" }
```

---

## Human-Review a Classification

```bash
# Correct the ambiguous message to the right label
curl -s -X PATCH http://localhost:8000/api/messages/$AMBIG_ID/classification/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"label":"service_question"}' | jq '{label, status, reviewed_by, reviewed_at}'
# Expected: { "label": "service_question", "status": "reviewed", "reviewed_by": "<your user id>", "reviewed_at": "<timestamp>" }
```

### Invalid label is rejected

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH \
  http://localhost:8000/api/messages/$AMBIG_ID/classification/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"label":"not_a_real_label"}'
# Expected: 422
```

### Reviewed label is protected from auto-overwrite

```bash
curl -s -X POST http://localhost:8000/api/messages/$AMBIG_ID/classify \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"force": false}' | jq '{label, status}'
# Expected: { "label": "service_question", "status": "reviewed" }  (unchanged)
```

---

## Outbound Messages Are Not Classified

```bash
# (If your simulator supports creating an outbound/agency message, do so, then:)
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/messages/$OUTBOUND_ID/classification \
  -H "Authorization: Bearer $TOKEN"
# Expected: 404 (NO_CLASSIFICATION) — outbound messages are never classified
```

---

## Tenant Isolation

```bash
# Login as a different tenant
ROYAL_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' \
  | jq -r .access_token)

# Try to read Elegant Weddings' classification as Royal Events staff
curl -s http://localhost:8000/api/messages/$MSG_ID/classification \
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

curl -s http://localhost:8000/api/messages/$MSG_ID/classification \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.error_code'
# Expected: "INSUFFICIENT_ROLE" (403)
```

---

## See It in the UI

1. Open the inbox at `http://localhost:5173/inbox` — Alice's row shows a `pricing_request` badge; the ambiguous one shows a "needs review" indicator (or "service_question" after you reviewed it).
2. Click into a conversation — the message detail page's **AI Intent** panel now shows the real label + confidence (replacing the Spec 005 placeholder). The other five panels remain "coming soon".
3. Use the review control on a needs-review message to set the correct label; the badge/panel update and the needs-review highlight clears.

---

## Run Tests

```bash
cd backend
pytest tests/integration/test_classification.py -v
pytest tests/unit/test_classifier_model.py -v
# Expected: all tests pass (AC-01 through AC-15)
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/classification.py
│   ├── services/classification_service.py
│   ├── ml/{classifier_model.py, loader.py, train_demo.py}
│   ├── models/classification.py
│   └── schemas/classification.py
├── alembic/versions/00xx_create_classification_results.py
├── models/intent/{vectorizer.joblib, model.joblib, labels.json, meta.json}
└── tests/{integration/test_classification.py, unit/test_classifier_model.py}

frontend/src/
├── api/classification.ts
├── types/classification.ts
└── components/classification/{IntentBadge.tsx, IntentPanel.tsx, ReviewControl.tsx}
```
