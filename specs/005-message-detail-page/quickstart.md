# Quickstart: Message Detail Page

**Branch**: `005-message-detail-page`

This guide covers testing the conversation detail endpoint locally, including 404/403 handling and mark-as-read behavior.

---

## Prerequisites

- Specs 001–004 fully implemented
- Backend running on `http://localhost:8000`
- Frontend running on `http://localhost:5173`
- At least one conversation with unread inbound messages (use the Spec 003 simulator)

---

## Seed a Conversation

```bash
# Login as Elegant Weddings staff
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

# Inject a message (creates a conversation with one unread inbound message)
CONV_ID=$(curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Alice Johnson","body":"Can you send me your wedding package prices?"}' \
  | jq -r .conversation_id)

echo "Conversation: $CONV_ID"
```

---

## Confirm It Is Unread (inbox before opening)

```bash
curl -s http://localhost:8000/api/v1/inbox \
  -H "Authorization: Bearer $TOKEN" | jq '{total_unread, items: [.items[] | {client_name, has_unread}]}'
# Expected: total_unread >= 1, Alice has_unread = true
```

---

## Open the Conversation Detail

```bash
curl -s http://localhost:8000/api/v1/conversations/$CONV_ID \
  -H "Authorization: Bearer $TOKEN" \
  | jq '{client_name, conversation_status, message_count: (.messages | length), first_msg: .messages[0] | {body, direction, status}, placeholders: (.ai_placeholders | keys)}'
```

**Expected**:
```json
{
  "client_name": "Alice Johnson",
  "conversation_status": "open",
  "message_count": 1,
  "first_msg": { "body": "Can you send me your wedding package prices?", "direction": "inbound", "status": "read" },
  "placeholders": ["escalation","intent","rag_sources","risk","suggested_reply","task_creation"]
}
```
Note: the inbound message's `status` is already `read` in the response — opening the detail marked it read.

---

## Verify Mark-as-Read Took Effect

```bash
# Inbox should now show Alice as read and total_unread decremented
curl -s http://localhost:8000/api/v1/inbox \
  -H "Authorization: Bearer $TOKEN" | jq '{total_unread, alice: [.items[] | select(.client_name=="Alice Johnson") | .has_unread]}'
# Expected: alice -> [false]; total_unread decreased by 1
```

---

## Verify Idempotency

```bash
# Opening again returns 200 and changes nothing
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/conversations/$CONV_ID \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200
```

---

## Test 404 — Non-Existent Conversation

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/v1/conversations/00000000-0000-0000-0000-000000000000 \
  -H "Authorization: Bearer $TOKEN"
# Expected: 404

curl -s http://localhost:8000/api/v1/conversations/00000000-0000-0000-0000-000000000000 \
  -H "Authorization: Bearer $TOKEN" | jq .error_code
# Expected: "CONVERSATION_NOT_FOUND"
```

---

## Test 403 — Cross-Tenant Access

```bash
# Login as Royal Events Agency (different tenant)
ROYAL_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' \
  | jq -r .access_token)

# Try to open Elegant Weddings' conversation as Royal Events staff
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/v1/conversations/$CONV_ID \
  -H "Authorization: Bearer $ROYAL_TOKEN"
# Expected: 403

curl -s http://localhost:8000/api/v1/conversations/$CONV_ID \
  -H "Authorization: Bearer $ROYAL_TOKEN" | jq .error_code
# Expected: "CROSS_TENANT_FORBIDDEN"
```

---

## Test 403 — Platform Admin Blocked

```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' \
  | jq -r .access_token)

curl -s http://localhost:8000/api/v1/conversations/$CONV_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE"
```

---

## Test tenant_id Injection Is Ignored

```bash
# Passing a bogus tenant_id query param must not change tenancy (derived from JWT)
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://localhost:8000/api/v1/conversations/$CONV_ID?tenant_id=99999999-9999-9999-9999-999999999999" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 (param ignored; JWT tenant used)
```

---

## Run Tests

```bash
cd backend
pytest tests/integration/test_conversation_detail.py -v
# Expected: all tests pass
```

---

## Frontend Check

1. Open the inbox at `http://localhost:5173/inbox`.
2. Click Alice Johnson's conversation row.
3. Verify the URL is `/conversations/{id}` and the page shows:
   - Client header (name, contact, status badge)
   - The message thread, oldest first
   - Six "Coming soon" panels: AI Intent, Risk / Sentiment, Knowledge Sources, Suggested Reply, Create Task, Escalate
4. Navigate back to the inbox — Alice's unread dot is gone.
5. Manually visit `/conversations/00000000-0000-0000-0000-000000000000` → "Conversation not found" view.

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/
│   │   └── conversations.py            # GET /api/v1/conversations/{id}
│   ├── services/
│   │   └── conversation_service.py     # get_conversation_detail() + mark_inbound_read()
│   └── schemas/
│       └── conversation.py             # MessageResponse, ConversationDetailResponse, AiPlaceholders
└── tests/
    └── integration/
        └── test_conversation_detail.py # AC-01 through AC-14

frontend/
└── src/
    ├── api/
    │   └── conversations.ts            # getConversationDetail(id)
    ├── hooks/
    │   └── useConversationDetail.ts    # fetch + loading/error/forbidden/notFound state
    ├── pages/
    │   └── ConversationDetailPage.tsx  # /conversations/:id (replaces Spec 004 stub)
    └── components/conversation/
        ├── ClientHeader.tsx
        ├── MessageThread.tsx
        ├── MessageBubble.tsx
        ├── AiPlaceholderPanel.tsx
        └── ConversationStates.tsx
```
