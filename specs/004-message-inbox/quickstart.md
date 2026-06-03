# Quickstart: Message Inbox

**Branch**: `004-message-inbox`

This guide covers testing the inbox endpoint locally after seeding it with simulator data.

---

## Prerequisites

- Specs 001–003 fully implemented (`alembic upgrade head` through migration 0010)
- Backend running on `http://localhost:8000`
- Frontend running on `http://localhost:5173`
- At least 2 simulator messages injected (see Spec 003 quickstart)

---

## Seed Some Inbox Data

```bash
# Login as Elegant Weddings staff
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

# Inject 3 conversations
for msg in \
  '{"client_name":"Alice Johnson","body":"Can you send me your wedding package prices?"}' \
  '{"client_name":"Bob Smith","body":"We need to change the guest count from 150 to 220."}' \
  '{"client_name":"Carol Davis","body":"I want to cancel. Is the deposit refundable?"}'; do
  curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$msg" | jq .is_new_conversation
done
# Expected: true true true
```

---

## View the Inbox

```bash
# Fetch inbox (all conversations)
curl -s http://localhost:8000/api/v1/inbox \
  -H "Authorization: Bearer $TOKEN" | jq '{total, total_unread, items: [.items[] | {client_name, has_unread, conversation_status}]}'
```

**Expected**:
```json
{
  "total": 3,
  "total_unread": 3,
  "items": [
    { "client_name": "Carol Davis",   "has_unread": true, "conversation_status": "open" },
    { "client_name": "Bob Smith",     "has_unread": true, "conversation_status": "open" },
    { "client_name": "Alice Johnson", "has_unread": true, "conversation_status": "open" }
  ]
}
```
(Ordered by most recently updated first.)

---

## Test Filters

```bash
# Unread only
curl -s "http://localhost:8000/api/v1/inbox?unread_only=true" \
  -H "Authorization: Bearer $TOKEN" | jq .total
# Expected: 3

# Filter by status=open
curl -s "http://localhost:8000/api/v1/inbox?status=open" \
  -H "Authorization: Bearer $TOKEN" | jq .total
# Expected: 3

# Filter by status=closed (none yet)
curl -s "http://localhost:8000/api/v1/inbox?status=closed" \
  -H "Authorization: Bearer $TOKEN" | jq .total
# Expected: 0
```

---

## Test Search

```bash
# Search by client name
curl -s "http://localhost:8000/api/v1/inbox?search=alice" \
  -H "Authorization: Bearer $TOKEN" | jq '[.items[].client_name]'
# Expected: ["Alice Johnson"]

# Search by message body
curl -s "http://localhost:8000/api/v1/inbox?search=cancel" \
  -H "Authorization: Bearer $TOKEN" | jq '[.items[].client_name]'
# Expected: ["Carol Davis"]

# Short search term (1 char) — should return 422
curl -s "http://localhost:8000/api/v1/inbox?search=a" \
  -H "Authorization: Bearer $TOKEN" | jq .detail
# Expected: 422 validation error
```

---

## Test Tenant Isolation

```bash
# Login as Royal Events Agency
ROYAL_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' \
  | jq -r .access_token)

# Royal Events inbox should be empty (no simulator messages injected there)
curl -s http://localhost:8000/api/v1/inbox \
  -H "Authorization: Bearer $ROYAL_TOKEN" | jq .total
# Expected: 0
```

---

## Test Role Access

```bash
# Platform Admin cannot access inbox
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' \
  | jq -r .access_token)

curl -s http://localhost:8000/api/v1/inbox \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE"
```

---

## Test Pagination

```bash
# Inject 22 more conversations (total 25), then verify pagination
curl -s "http://localhost:8000/api/v1/inbox?page=1" \
  -H "Authorization: Bearer $TOKEN" | jq '{total, total_pages, page, item_count: (.items | length)}'
# Expected: { "total": 25, "total_pages": 2, "page": 1, "item_count": 20 }

curl -s "http://localhost:8000/api/v1/inbox?page=2" \
  -H "Authorization: Bearer $TOKEN" | jq '.items | length'
# Expected: 5
```

---

## Run Tests

```bash
cd backend
pytest tests/integration/test_inbox.py -v
# Expected: all tests pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/
│   │   └── inbox.py                   # GET /api/v1/inbox
│   ├── services/
│   │   └── inbox_service.py           # get_inbox() + truncate_preview()
│   └── schemas/
│       └── inbox.py                   # InboxFilters, InboxItemResponse, InboxResponse
└── tests/
    └── integration/
        └── test_inbox.py              # AC-01 through AC-15 integration tests

frontend/
└── src/
    ├── api/
    │   └── inbox.ts                   # getInbox(params) Axios call
    ├── hooks/
    │   └── useInbox.ts                # filter state + fetch + URLSearchParams sync
    ├── pages/
    │   └── InboxPage.tsx              # /inbox route
    └── components/inbox/
        ├── InboxFilters.tsx           # read-status toggle + status select
        ├── InboxSearch.tsx            # debounced search input
        ├── InboxList.tsx              # list wrapper + empty state logic
        ├── InboxItem.tsx              # single conversation card
        ├── InboxEmptyState.tsx        # global-empty + filtered-empty variants
        └── InboxPagination.tsx        # previous/next + page indicator
```
