# Quickstart: Short-Term Conversation Memory

**Branch**: `016-short-term-memory`

This guide shows a developer how to manually verify tenant-scoped short-term memory: that it resolves recent references ("that", "it", "the package", "the guest count", "the deposit"), that **RAG remains the source of truth**, that **Tenant A can never read Tenant B memory**, that memory **expires/clears**, and that **PII is redacted**. Memory is an **enrichment** of the existing RAG (009) + suggested-reply (010) step — it is best-effort, temporary (default 7-day TTL), redacted, and never auto-sends or auto-creates anything.

Steps:
1. Create a conversation with a guest-count change.
2. Add a follow-up message: "Will that affect the price?"
3. Confirm memory resolves "that" as the guest-count change.
4. Confirm RAG is still required for the price/policy answer.
5. Confirm Tenant 1 cannot access Tenant 2 memory.
6. Confirm memory expires or can be cleared.
7. Confirm PII is minimized/redacted in summaries.

---

## Prerequisites

- Specs 001–010, 013, 014 implemented and migrated (auth, conversations/messages, RAG, suggested replies, audit, guardrails)
- **Redis** running and reachable at `REDIS_URL`
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`
- `MEMORY_ENABLED=true`, `MEMORY_TTL_SECONDS=604800` (7 days), `MEMORY_MAX_RECENT_MESSAGES=10`, `MEMORY_SUMMARY_MAX_CHARS=1000`
- Two seeded tenants (Tenant 1 = `elegant-weddings`, Tenant 2 = `royal-events`) each with a **staff** user and at least one processed pricing/catering document for RAG

---

## Login + helpers

```bash
T1=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
T2=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"staff@royal-events.demo","password":"staff-password-2","tenant_slug":"royal-events"}' | jq -r .access_token)

# Send a simulated inbound message (Spec 003). $1=token $2=json-body
sendmsg () { curl -s -X POST http://localhost:8000/api/simulator/messages \
  -H "Authorization: Bearer $1" -H "Content-Type: application/json" -d "$2"; }
# Get a conversation's memory. $1=token $2=conversation_id
getmem () { curl -s "http://localhost:8000/api/conversations/$2/memory" -H "Authorization: Bearer $1"; }
```

---

## Step 1 — Create a conversation with a guest-count change

```bash
# First client message creates the conversation (Spec 003 returns conversation_id + message_id):
R1=$(sendmsg "$T1" '{"client_name":"Dana K.","body":"We need to increase the guest count from 150 to 220."}')
CONV=$(echo "$R1" | jq -r '.conversation_id')
echo "conversation: $CONV"
```
**Expected**: a conversation is created with the first inbound message stored. Opening/processing the message triggers `memory.update_from_message` (best-effort), building the digest.

---

## Step 2 — Add a follow-up message: "Will that affect the price?"

```bash
sendmsg "$T1" "{\"conversation_id\":\"$CONV\",\"body\":\"Will that affect the price?\"}" | jq '{message_id, conversation_id}'
```
**Expected**: the second inbound message is appended to the same conversation; memory updates again from the recent window.

---

## Step 3 — Confirm memory resolves "that" as the guest-count change

```bash
getmem "$T1" "$CONV" | jq '{status, summary, anchors: .metadata, refs: [.recent_message_refs[] | {content_summary, metadata}]}'
```
**Expected**: `status:"active"`; the `summary` mentions the **guest-count increase 150 → 220**; a `recent_message_refs` entry has `metadata.anchor = "guest_count"` (`from:150`, `to:220`). This is the antecedent that lets the AI resolve **"that"**.

Now generate a suggested reply for the follow-up message and confirm the context is used:
```bash
# Spec 010 generate (memory is fetched internally via memory.get_context and passed as supporting context)
curl -s -X POST "http://localhost:8000/api/messages/$MSG2/suggested-reply" \
  -H "Authorization: Bearer $T1" | jq '{used_memory: .debug.memory_used, draft: .generated_text}'
# Expected: the draft understands "that" = the guest-count increase (references raising to 220 guests).
```

---

## Step 4 — Confirm RAG is still required for the price/policy answer

```bash
curl -s -X POST "http://localhost:8000/api/messages/$MSG2/suggested-reply" \
  -H "Authorization: Bearer $T1" | jq '{rag_sources: [.sources[]?.document_title], draft: .generated_text}'
```
**Expected**:
- RAG (009) is **still queried** — `sources` lists the tenant's pricing/catering policy documents. Memory is **supporting context only**; RAG is the **source of truth**.
- If the documents **do not** state a price for 220 guests, the draft **does not invent one** (014 grounding) — it reflects what the sources support or asks to confirm. **No fabricated price.**
- **Conflict check**: if memory held a contradictory claim (e.g., "you told me catering is free over 200"), the draft follows the **document**, not the memory (RAG wins).

**Unverifiable-claim variant** (deposit example):
```bash
sendmsg "$T1" "{\"conversation_id\":\"$CONV\",\"body\":\"I paid the deposit yesterday.\"}" >/dev/null
sendmsg "$T1" "{\"conversation_id\":\"$CONV\",\"body\":\"Can you confirm it?\"}" >/dev/null
getmem "$T1" "$CONV" | jq '.recent_message_refs[] | select(.metadata.fact=="deposit_paid") | .metadata'
# Expected: { "fact": "deposit_paid", "verified": false }
# The suggested reply resolves "it" = the deposit but must NOT claim payment is confirmed —
# it suggests checking/confirming instead (no false confirmation).
```

---

## Step 5 — Confirm Tenant 1 cannot access Tenant 2 memory

```bash
# Tenant 2 tries to read Tenant 1's conversation memory:
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/conversations/$CONV/memory" -H "Authorization: Bearer $T2"
# Expected: 404 (conversation not in caller's tenant; the Redis key is never even constructed)

# Sanity: the Redis key embeds the tenant id, so a conversation_id alone can't address another tenant's memory:
redis-cli KEYS "mem:*:$CONV" | sed 's/:[^:]*$//' | sort -u
# Expected: exactly one key, prefixed mem:<tenant1_id>:...  (never a tenant2-prefixed key)
```
**Expected**: cross-tenant memory read is blocked (404); keys are tenant-prefixed (`mem:{tenant_id}:{conversation_id}`), so Tenant 2 can never reach Tenant 1's digest. A **platform admin** token would get **403** (no tenant-content access).

---

## Step 6 — Confirm memory expires or can be cleared

```bash
# Check the TTL Redis is enforcing (~7 days = 604800s):
KEY=$(redis-cli KEYS "mem:*:$CONV" | head -1)
redis-cli TTL "$KEY"
# Expected: a positive number near 604800 (default 7-day TTL)

# Clear the memory explicitly:
curl -s -X DELETE "http://localhost:8000/api/conversations/$CONV/memory" -H "Authorization: Bearer $T1" | jq
# Expected: { "conversation_id": "...", "cleared": true, "status": "cleared" }

# A subsequent read is cold/empty:
getmem "$T1" "$CONV" | jq '{status, summary, refs: (.recent_message_refs|length)}'
# Expected: status "expired"/"cleared", summary "", refs 0

# Rebuild on demand from the recent window:
curl -s -X POST "http://localhost:8000/api/conversations/$CONV/memory/refresh" -H "Authorization: Bearer $T1" | jq
# Expected: { "status": "active", "updated_at": "...", "expires_at": "...(+7d)", "entry_count": >=1 }
```

**Degraded-mode check** (memory is optional): stop Redis (or set `MEMORY_ENABLED=false`) and regenerate a reply:
```bash
curl -s -X POST "http://localhost:8000/api/messages/$MSG2/suggested-reply" -H "Authorization: Bearer $T1" | jq '.status'
# Expected: a reply is still generated (memory-less, RAG-grounded). GET memory returns status "disabled". No 5xx.
```

---

## Step 7 — Confirm PII is minimized/redacted in summaries

```bash
# Send a message containing an email + phone:
sendmsg "$T1" "{\"conversation_id\":\"$CONV\",\"body\":\"Reach me at dana.k@example.com or +961 70 123 456 about the deposit.\"}" >/dev/null
curl -s -X POST "http://localhost:8000/api/conversations/$CONV/memory/refresh" -H "Authorization: Bearer $T1" >/dev/null

getmem "$T1" "$CONV" | jq '{pii: .metadata.pii_redacted,
  summary, refs: [.recent_message_refs[] | {content_summary, pii_redacted}]}'
# Expected: metadata.pii_redacted = true; summary + content_summary contain [EMAIL_REDACTED]/[PHONE_REDACTED],
#           never the raw email/phone.

# Scan the digest for any raw PII / secret leakage:
getmem "$T1" "$CONV" | jq -r '(.summary) + ([.recent_message_refs[].content_summary]|join(" ")) | ascii_downcase' \
  | grep -Eo "@example\.com|\\+961|sk-[a-z0-9]|bearer |eyj[a-z0-9]" | wc -l
# Expected: 0  (redacted in + out)

# Confirm nothing is persisted to Postgres (memory is Redis-only, ephemeral):
psql "$DATABASE_URL" -c "\dt" | grep -i memory | wc -l
# Expected: 0  (no conversation_memory table; the digest lives only in Redis with a TTL)
```

**Audit check** (memory use is reviewable, redacted):
```bash
curl -s "http://localhost:8000/api/audit-logs?event_type=memory_used_in_reply" -H "Authorization: Bearer $T1" \
  | jq '.items[0] | {event_type, conversation_id: .entity_id, metadata}'
# Expected: a redacted entry (ids/facts only, no raw PII); also memory_viewed/memory_refreshed/memory_cleared exist.
```

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_memory_redact_summarize.py tests/unit/test_memory_keys.py \
       tests/unit/test_memory_degraded.py tests/unit/test_memory_unverified_claim.py -v
pytest tests/integration/test_conversation_memory.py -v   # AC-01..AC-20
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/conversation_memory.py            # GET / POST refresh / DELETE
│   ├── services/
│   │   ├── memory_service.py                    # get_context / update_from_message / redact_and_summarize / view / refresh / clear
│   │   └── memory_store.py                       # Redis adapter: keys (tenant-embedded) + TTL + bounded list + graceful degradation
│   ├── schemas/memory.py                         # MemoryStatus / MemorySource + view/context DTOs
│   └── core/{config.py (MEMORY_*), redis.py}     # settings + async Redis lifecycle
│   └── services/suggested_reply_service.py (010) # MODIFIED: fetch get_context; memory as supporting context, RAG authoritative
└── tests/{unit/test_memory_*.py, integration/test_conversation_memory.py}

frontend/src/ (optional)
├── api/conversationMemory.ts
├── types/memory.ts
└── components/conversation/RecentContextChip.tsx # read-only redacted "recent context" on the detail page (005)
```

> Reminder: memory is **supporting context, not a source of truth**. RAG documents (009) remain authoritative for package/pricing/refund/cancellation/contract answers; on any conflict, RAG wins; the AI never invents an unsupported price or fabricates a confirmation.
