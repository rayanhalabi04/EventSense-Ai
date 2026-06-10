# Demo RAG Document Packs

This folder contains the demo document packs used to test and demo EventSense AI's
**tenant-scoped RAG** feature. Each tenant retrieves answers only from its own
uploaded documents, so these packs are deliberately different between the two demo
tenants to make tenant isolation easy to prove.

## Why these documents are fictional

All content here is **fictional sample material** created specifically for this demo.
It does not use copyrighted text from any real company and does not represent any real
business's policies, pricing, or contracts. Prices are in unnamed "currency units" and
all policies were written from scratch for testing.

## Folder → tenant mapping

| Folder              | Tenant                 | Tenant slug            | Manager login                                  |
| ------------------- | ---------------------- | ---------------------- | ---------------------------------------------- |
| `elegant_weddings/` | Elegant Weddings       | `elegant-weddings`     | `admin@elegant-weddings.demo` / `demo-password-1` |
| `royal_events/`     | Royal Events Agency    | `royal-events-agency`  | `admin@royal-events.demo` / `demo-password-2`     |

Each folder contains six documents:

| File                      | Title (as uploaded)            | document_type          |
| ------------------------- | ------------------------------ | ---------------------- |
| `pricing_packages.md`     | `<Tenant> Pricing & Packages`  | `package`*             |
| `deposit_policy.md`       | `<Tenant> Deposit Policy`      | `deposit_policy`       |
| `cancellation_policy.md`  | `<Tenant> Cancellation Policy` | `cancellation_policy`  |
| `guest_count_policy.md`   | `<Tenant> Guest Count Policy`  | `service_description`  |
| `services_faq.md`         | `<Tenant> FAQ`                 | `faq`                  |
| `contract_terms.md`       | `<Tenant> Contract Terms`      | `contract_terms`       |

\* The original task spec asked for `pricing_package`, but the backend
`DocumentType` enum has no such value (it exposes `pricing` and `package`).
`pricing_packages.md` is therefore uploaded as `package`, the closest valid value.

## How the two tenants differ (what to demo)

| Topic                         | Elegant Weddings                                        | Royal Events Agency                                                          |
| ----------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------- |
| Deposit refundability         | Non-refundable after booking confirmation               | Partially refundable if cancelled >30 days out; non-refundable within 30 days |
| Guest count deadline          | Confirm changes at least **10 days** before the event   | Changes allowed up to **7 days** before the event                           |
| Late guest-count increases    | Require **manager approval**                            | Require **catering and venue approval**                                      |
| Final balance due             | **14 days** before the event                            | **10 days** before the event                                                |
| Top package inclusions        | Premium: decoration, catering coord., photography coord. | Luxury: decoration, catering, lighting, bridal entrance setup               |
| Airport transportation        | Not provided unless added as a **custom service**       | VIP airport transportation available only as a **paid add-on**             |
| Escalation style              | Custom/unsupported requests → **staff review**          | High-risk client complaints → **manager**                                   |

## How to run the seed script

Start the dockerized stack first (see the project docker setup), then run:

```bash
# Default API base URL is http://localhost:8088
scripts/seed_rag_documents.sh

# Override the API base URL if your API is on a different port
API_BASE_URL=http://localhost:8000 scripts/seed_rag_documents.sh
```

The script logs in as each tenant manager and uploads that tenant's six documents.
It checks the existing document list first and **skips any document whose title
already exists**, so it is safe to re-run. It prints `[OK]`, `[SKIP]`, or `[FAIL]`
per document and exits non-zero if any login or upload fails.

> Note: the seed script defaults to `http://localhost:8088`. If you brought the stack
> up with the default API port, use `API_BASE_URL=http://localhost:8000`. (See the
> repo's port-override notes if 8000 is occupied locally.)

## Manual RAG testing with curl

Set your API base URL first:

```bash
export API="http://localhost:8088"   # or http://localhost:8000
```

### 1. Log in as Elegant Weddings

```bash
ELEGANT_TOKEN=$(curl -s -X POST "$API/auth/token" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@elegant-weddings.demo","password":"demo-password-1","tenant_slug":"elegant-weddings"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

### 2. Ask Elegant about deposit refundability

```bash
curl -s -X POST "$API/api/v1/rag/query" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ELEGANT_TOKEN" \
  -d '{"query":"Is the deposit refundable after booking confirmation?"}'
```

**Expected:** retrieves the Elegant Weddings Deposit Policy; the deposit is
**non-refundable after booking confirmation**.

### 3. Log in as Royal Events

```bash
ROYAL_TOKEN=$(curl -s -X POST "$API/auth/token" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@royal-events.demo","password":"demo-password-2","tenant_slug":"royal-events-agency"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

### 4. Ask Royal about the 30-day refund window

```bash
curl -s -X POST "$API/api/v1/rag/query" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ROYAL_TOKEN" \
  -d '{"query":"Is the deposit refundable if I cancel more than 30 days before the event?"}'
```

**Expected:** retrieves the Royal Events Deposit Policy; the deposit is **partially
refundable** when cancelling more than 30 days before the event.

### 5. Airport transportation for each tenant

```bash
# Elegant
curl -s -X POST "$API/api/v1/rag/query" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ELEGANT_TOKEN" \
  -d '{"query":"Do you provide airport transportation for guests?"}'

# Royal
curl -s -X POST "$API/api/v1/rag/query" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ROYAL_TOKEN" \
  -d '{"query":"Can you arrange airport transportation for VIP guests?"}'
```

**Expected — Elegant:** not provided unless added as a custom service.
**Expected — Royal:** VIP airport transportation can be arranged as a paid add-on.

## Example demo questions

### Elegant Weddings

- "Is the deposit refundable after booking confirmation?"
- "When do I need to confirm my final guest count?"
- "What's included in the Premium package?"
- "Do you provide airport transportation for guests?"
- "When is the final balance due?"
- "How late can I change my decoration samples?"

### Royal Events Agency

- "Is the deposit refundable if I cancel more than 30 days before the event?"
- "How late can I change my guest count?"
- "What's included in the Luxury package?"
- "Can you arrange airport transportation for VIP guests?"
- "When is the final balance due?"
- "How late can I change the lighting setup?"

## Proving tenant isolation

Ask the **same** question of both tenants and confirm each answer comes only from its
own documents and reflects that tenant's facts — for example, asking the guest-count
deadline returns **10 days** for Elegant and **7 days** for Royal. Sources returned by
`/api/v1/rag/query` always belong to the authenticated tenant; neither tenant can ever
retrieve the other's documents.
