# Quickstart: Suggested Replies

**Branch**: `010-suggested-replies`

This guide shows a developer how to test AI suggested replies manually across five scenarios, using the two demo tenants from earlier specs. Suggested replies depend on the full upstream chain: **message → intent (006) → risk (007) → RAG (009) → suggested reply**.

Scenarios:
1. Pricing request with a matching package document (grounded).
2. Cancellation request with a matching cancellation policy (grounded, high-risk).
3. Unsupported question with no matching document (refusal).
4. High-risk complaint requiring careful wording.
5. Tenant isolation — Tenant 1 cannot use Tenant 2 sources.

---

## Prerequisites

- Specs 001–009 implemented and migrated (documents uploaded + processed for RAG; intent + risk produced on message creation)
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`
- A generation model configured (or the deterministic test stub enabled)

---

## Run Migrations

```bash
cd backend
alembic upgrade head
# Applies the create_suggested_replies migration
```

---

## Login + helpers

```bash
EW=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
RE=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events-agency"}' | jq -r .access_token)

# Inject a client message (auto-classifies + risk + makes it ready for RAG/reply)
inject () {  # $1=token $2=body -> echoes message id
  curl -s -X POST http://localhost:8000/api/v1/simulator/messages \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "$(jq -n --arg b "$2" '{client_name:"Demo Client", body:$b}')" \
    | jq -r '.message_id // .latest_message_id // .id'
}

generate () {  # $1=token $2=message_id
  curl -s -X POST http://localhost:8000/api/messages/$2/suggested-replies \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" -d '{}' \
    | jq '{status, grounded, sources: [.sources[].document_title], text: .generated_text}'
}
```

> Ensure the relevant documents are uploaded **and processed** (Spec 009 `POST /documents/{id}/process`) for each tenant before generating, so RAG has chunks to retrieve.

---

## Scenario 1 — Pricing request with matching package document (grounded)

```bash
M1=$(inject "$EW" "Can you send me your wedding package prices?")
generate "$EW" "$M1"
```
**Expected**:
```json
{
  "status": "draft_generated",
  "grounded": true,
  "sources": ["Premium Wedding Package"],
  "text": "Thank you for your interest! Our Premium Wedding Package includes ... (per our Premium Wedding Package)."
}
```
The draft references the package document; sources are non-empty.

---

## Scenario 2 — Cancellation request with matching cancellation/deposit policy (grounded, high-risk)

```bash
M2=$(inject "$EW" "I want to cancel the booking. Is the deposit refundable?")
generate "$EW" "$M2"
```
**Expected**:
```json
{
  "status": "draft_generated",
  "grounded": true,
  "sources": ["Deposit Policy", "Cancellation Policy"],
  "text": "I'm sorry to hear you're considering cancelling. According to our Deposit Policy, ... I'd be happy to help further."
}
```
Careful tone (high risk) + grounded in the deposit/cancellation policy. The draft may note that the case can be escalated to a manager — but no escalation is created.

---

## Scenario 3 — Unsupported question, no matching document (refusal — must not invent)

```bash
M3=$(inject "$EW" "Can you organize fireworks with drones and celebrity singers?")
generate "$EW" "$M3"
```
**Expected**:
```json
{
  "status": "draft_generated",
  "grounded": false,
  "sources": [],
  "text": "Thank you for reaching out! That isn't covered in our current documents, so I'd like to confirm the details with our team before giving you an exact answer. Someone will follow up shortly."
}
```
No invented policy/price/availability; empty sources; `grounded:false`. This is the mandated refuse path.

---

## Scenario 4 — High-risk complaint requiring careful wording

```bash
M4=$(inject "$EW" "I am very unhappy with the decoration sample and the wedding is next week.")
generate "$EW" "$M4"
```
**Expected** (careful, empathetic; may recommend escalation; no escalation created):
```json
{
  "status": "draft_generated",
  "grounded": false,
  "sources": [],
  "text": "I'm truly sorry the decoration sample didn't meet your expectations, especially so close to your wedding. Your satisfaction matters to us and I'm escalating this to our team to resolve it urgently..."
}
```
Verify the tone is empathetic and de-escalating, and that **no task or escalation entity is created** by this call.

---

## Scenario 5 — Tenant isolation (Tenant 1 cannot use Tenant 2 sources)

```bash
# Same pricing question for both tenants
ME=$(inject "$EW" "Can you send me your wedding package prices?")
MR=$(inject "$RE" "Can you send me your wedding package prices?")

echo "Elegant Weddings:"; generate "$EW" "$ME"
echo "Royal Events:";     generate "$RE" "$MR"
```
**Expected**:
- Elegant Weddings draft cites **Premium Wedding Package** (EW) only.
- Royal Events draft cites **Luxury Wedding Package** (RE) only.
- Neither draft references the other tenant's documents.

Cross-tenant reply access is blocked:
```bash
# Get an EW reply id, then try to read it as Royal Events
EW_REPLY=$(curl -s http://localhost:8000/api/messages/$ME/suggested-replies \
  -H "Authorization: Bearer $EW" | jq -r '.items[0].id')

curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/suggested-replies/$EW_REPLY \
  -H "Authorization: Bearer $RE"
# Expected: 403 (CROSS_TENANT_FORBIDDEN)
```

---

## Human Review: edit → approve / reject (no send)

```bash
REPLY=$(curl -s http://localhost:8000/api/messages/$M1/suggested-replies \
  -H "Authorization: Bearer $EW" | jq -r '.items[0].id')

# Edit
curl -s -X PATCH http://localhost:8000/api/suggested-replies/$REPLY \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" \
  -d '{"edited_text":"Hi! Our Premium package starts at £4,500 and includes full-day coordination. Shall I send the full brochure?"}' \
  | jq '{status, effective_text}'
# Expected: status "edited", effective_text = the edit (generated_text preserved)

# Approve (human-accept; NOT sent)
curl -s -X POST http://localhost:8000/api/suggested-replies/$REPLY/approve \
  -H "Authorization: Bearer $EW" | jq '{status, approved_by, approved_at}'
# Expected: status "approved", approved_by + approved_at set

# Editing an approved reply is blocked
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH http://localhost:8000/api/suggested-replies/$REPLY \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" -d '{"edited_text":"too late"}'
# Expected: 422 (INVALID_STATE_TRANSITION)
```

Reject path:
```bash
R2=$(curl -s -X POST http://localhost:8000/api/messages/$M2/suggested-replies \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" -d '{"force":true}' | jq -r '.id')
curl -s -X POST http://localhost:8000/api/suggested-replies/$R2/reject \
  -H "Authorization: Bearer $EW" -H "Content-Type: application/json" -d '{"reason":"rewriting"}' | jq '.status'
# Expected: "rejected"
```

---

## Precondition + Role checks

```bash
# Platform Admin blocked
ADMIN=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' | jq -r .access_token)
curl -s -X POST http://localhost:8000/api/messages/$M1/suggested-replies \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{}' | jq .error_code
# Expected: "INSUFFICIENT_ROLE"

# Missing upstream (a message with no classification/risk yet) -> precondition error
# (Use a message created before specs 006/007 ran, if available)
# Expected: 409 PRECONDITION_NOT_MET
```

---

## See It in the UI

1. Open a conversation at `http://localhost:5173/conversations/<conversation_id>`.
2. The **Suggested Reply** panel (replacing the Spec 005 placeholder) shows the draft, a grounded/refusal indicator, the cited sources (title + type + snippet), and a status badge.
3. Edit the text, then Approve or Reject. Approve records the reviewer; nothing is sent. The other placeholders (Create Task, Escalate) remain "coming soon".

---

## Run Tests + Eval

```bash
cd backend
pytest tests/unit/test_reply_prompt.py tests/unit/test_reply_service.py -v
pytest tests/integration/test_suggested_replies.py -v   # AC-01..AC-18
pytest tests/eval/test_reply_grounding.py -v            # grounded cites right tenant source; refusal fires; no cross-tenant source
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/suggested_replies.py
│   ├── services/suggested_reply_service.py
│   ├── ai/{reply_generator.py, reply_prompt.py}
│   ├── models/suggested_reply.py
│   └── schemas/suggested_reply.py
├── alembic/versions/00xx_create_suggested_replies.py
└── tests/{unit/test_reply_prompt.py, unit/test_reply_service.py,
          integration/test_suggested_replies.py, eval/test_reply_grounding.py}

frontend/src/
├── api/suggestedReplies.ts
├── types/suggestedReply.ts
└── components/replies/{SuggestedReplyPanel.tsx, ReplyEditor.tsx, ReplySources.tsx}
```
