# Quickstart: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator`

This guide covers how to run the simulator locally, inject test messages, and verify tenant isolation.

---

## Prerequisites

- Specs 001 and 002 fully implemented and running (`alembic upgrade head` through migration 0009)
- Backend running on `http://localhost:8000`
- Frontend running on `http://localhost:5173`
- Demo tenant credentials available (see Spec 002 quickstart)

---

## Apply the Message Status Migration

```bash
cd backend
alembic upgrade head   # applies migration 0010_create_conversations_messages
```

Verify:
```bash
psql $DATABASE_URL -c "\d messages"
# Expected: 'status' column of type 'message_status' with default 'unread'
```

---

## Inject a Simulator Message (curl)

```bash
# Login as Elegant Weddings staff
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

# Inject a simulated message
curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Alice Johnson",
    "client_contact": "+44 7700 900123",
    "body": "Can you send me your wedding package prices?"
  }' | jq .
```

**Expected response**:
```json
{
  "message_id": "<uuid>",
  "conversation_id": "<uuid>",
  "is_new_conversation": true,
  "conversation_status": "open",
  "tenant_id": "a1b2c3d4-0000-0000-0000-000000000001"
}
```

---

## Inject a Follow-Up Message (existing conversation)

```bash
# Get the conversation_id from the first response, then inject a follow-up
CONV_ID="<paste conversation_id from above>"

curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"body\": \"We need to change the guest count from 150 to 220.\"
  }" | jq .
# Expected: is_new_conversation=false, same conversation_id
```

---

## Test Validation

```bash
# Empty body — should return 422
curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Alice","body":"   "}' | jq .status
# Expected: 422

# Platform admin cannot use simulator — should return 403
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' \
  | jq -r .access_token)

curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Alice","body":"test"}' | jq .error_code
# Expected: "INSUFFICIENT_ROLE"
```

---

## Verify Tenant Isolation

```bash
# Login as Royal Events Agency
ROYAL_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' \
  | jq -r .access_token)

# Try to inject into Elegant Weddings conversation using Royal Events token
CONV_ID="<Elegant Weddings conversation_id from above>"
curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $ROYAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\": \"$CONV_ID\", \"body\": \"cross-tenant attempt\"}" \
  | jq .error_code
# Expected: "CROSS_TENANT_ACCESS"
```

---

## Run Tests

```bash
cd backend
pytest tests/integration/test_simulator.py -v
# Expected: all tests pass
```

---

## Use the Simulator UI

1. Navigate to `http://localhost:5173/simulator`
2. You should see the `SimulatorPage` with 5 preset chips
3. Click a preset — the message body field should populate
4. Enter a client name and submit
5. Verify the confirmation message shows the conversation ID
6. Submit a second message for the same client — verify `is_new_conversation=false` in the network tab

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/
│   │   └── simulator.py               # POST /api/v1/simulator/messages
│   │                                  # GET  /api/v1/simulator/conversations
│   ├── services/
│   │   └── simulator_service.py       # Conversation resolve + message create logic
│   └── schemas/
│       └── simulator.py               # SimulatorMessageRequest, SimulatorMessageResponse
├── alembic/versions/
│   └── 0010_create_conversations_messages.py
└── tests/
    └── integration/
        └── test_simulator.py          # AC-01 through AC-12 integration tests

frontend/
└── src/
    ├── data/
    │   └── simulatorPresets.ts        # SIMULATOR_PRESETS constant
    ├── api/
    │   └── simulator.ts               # injectMessage(), listConversations() API calls
    ├── pages/
    │   └── SimulatorPage.tsx          # /simulator route
    └── components/simulator/
        ├── SimulatorForm.tsx          # Full form with client fields + body + submit
        ├── PresetPicker.tsx           # Horizontal chip row for 5 presets
        ├── ConversationSelector.tsx   # Dropdown of existing tenant conversations
        └── CharacterCounter.tsx       # Live counter for message body
```
