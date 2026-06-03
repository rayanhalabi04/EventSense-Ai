# Feature Specification: Multi-Tenant Workspace

**Feature Branch**: `004-multi-tenant-workspace`

**Created**: 2026-06-03

**Status**: Draft

**Input**: User description: "Multi-Tenant Workspace for EventSense AI — a multi-tenant AI dashboard for wedding planners and event agencies supporting isolated tenants with full data separation and secure AI operations."

---

## Goal

Enable EventSense AI to serve multiple independent tenants (wedding planning agencies and event companies) from a single platform instance, while guaranteeing complete data isolation between tenants. Every piece of data — messages, documents, AI-generated suggestions, tasks, and audit logs — is scoped to exactly one tenant and is never accessible to users of another tenant.

The MVP must support at least two demo tenants: **Elegant Weddings** and **Royal Events Agency**.

---

## Main Users

| Role | Description |
|------|-------------|
| **Tenant Admin** | Owner or manager of a specific agency. Can manage their own users, view audit logs, and configure tenant settings. Cannot access or see any other tenant's data. |
| **Tenant Agent** | A planner or staff member within a tenant. Can handle client messages, use AI suggestions, create tasks, and upload documents — all within their tenant. |
| **Platform Super Admin** | Internal operator of EventSense AI. Can provision new tenants and manage platform-level settings. Cannot read tenant content data. |

---

## User Stories

### User Story 1 — Tenant-Isolated Login and Dashboard (Priority: P1)

A wedding planner at Elegant Weddings logs in and lands on a dashboard that shows only their agency's conversations, messages, and tasks. They have no visibility into Royal Events Agency's data, and no option to switch to another tenant.

**Why this priority**: This is the foundational capability. Without it, no other feature can safely operate. All downstream AI features depend on the authenticated user's tenant context being established first.

**Independent Test**: Can be fully tested by creating two tenants with separate users, logging in as each, and verifying the dashboard only shows that tenant's data — with zero records from the other tenant ever appearing.

**Acceptance Scenarios**:

1. **Given** a planner is authenticated as an Elegant Weddings user, **When** they load the dashboard, **Then** only Elegant Weddings conversations, messages, and tasks are visible.
2. **Given** a planner is authenticated as an Elegant Weddings user, **When** they attempt to navigate to a URL or ID belonging to Royal Events Agency, **Then** they receive an access-denied response and the attempt is logged.
3. **Given** a user exists in both tenants (edge case), **When** they log in, **Then** they must explicitly select which tenant context to enter before the session is established.

---

### User Story 2 — Tenant-Scoped Document Upload and RAG Retrieval (Priority: P1)

A planner uploads a wedding contract PDF or a venue information sheet. The document is stored and indexed exclusively within their tenant's knowledge base. When the AI generates suggested replies or retrieves context, it only draws from documents belonging to that tenant.

**Why this priority**: RAG retrieval is the primary source of AI accuracy in this product. A cross-tenant document leak would be both a privacy failure and a business-critical bug. This must be enforced from day one.

**Independent Test**: Upload a document to Tenant A. Ask the AI to answer a question that only that document can answer, while authenticated as Tenant B. The AI must return no relevant answer from Tenant A's document.

**Acceptance Scenarios**:

1. **Given** Tenant A has uploaded a document containing unique content, **When** Tenant B's AI agent retrieves context for a query matching that content, **Then** no chunks from Tenant A's document are returned.
2. **Given** a planner uploads a PDF, **When** the document is processed, **Then** every chunk stored in the RAG knowledge base carries the uploader's `tenant_id`.
3. **Given** a planner queries the AI, **When** the RAG system retrieves context, **Then** only chunks where `tenant_id` matches the authenticated user's tenant are considered.

---

### User Story 3 — Tenant-Scoped AI Suggested Replies (Priority: P2)

When a client sends a message, the AI generates reply suggestions based only on that tenant's documents, past conversations, and knowledge base. Suggestions never reference or incorporate information from another tenant's data.

**Why this priority**: Suggested replies are the core AI value proposition. They depend on tenant-isolated RAG (P1) being in place. Failures here would produce incorrect or confidential suggestions.

**Independent Test**: Configure Tenant A with a unique pricing sheet. Log in as Tenant B and trigger a reply suggestion for a similar query. Verify the response contains no data or phrasing unique to Tenant A's documents.

**Acceptance Scenarios**:

1. **Given** the AI generates a reply for a Tenant B conversation, **When** the reply is produced, **Then** it cites only sources retrieved from Tenant B's knowledge base.
2. **Given** a suggested reply is stored, **When** it is persisted, **Then** it is associated with the correct `tenant_id` and `conversation_id`.
3. **Given** a tenant has no uploaded documents, **When** the AI generates a suggested reply, **Then** the reply is generated from general knowledge without leaking another tenant's documents.

---

### User Story 4 — Cross-Tenant Access Blocking and Audit Logging (Priority: P2)

Any attempt by an authenticated user to access data belonging to another tenant is automatically blocked at the API layer. The attempt is recorded in an immutable audit log accessible only to the Platform Super Admin and the affected tenant's admin.

**Why this priority**: Provides the security guarantee that completes the isolation model. Audit logs create accountability and enable breach detection.

**Independent Test**: Authenticated as Tenant A, issue an API request using a resource ID owned by Tenant B. Verify the request is rejected with a permission error. Verify an audit log entry is created containing the actor, the resource attempted, and the timestamp.

**Acceptance Scenarios**:

1. **Given** an authenticated Tenant A user, **When** they request a resource whose `tenant_id` is Tenant B, **Then** the system returns a permission-denied error and does not expose any data.
2. **Given** a cross-tenant access attempt occurs, **When** the system blocks it, **Then** an audit log entry is created with: actor identity, target resource, action attempted, timestamp, and outcome.
3. **Given** a Tenant Admin views their audit log, **When** they filter by security events, **Then** they see only events related to their own tenant.

---

### User Story 5 — Tenant Provisioning by Super Admin (Priority: P3)

A Platform Super Admin creates a new tenant (e.g., "Elegant Weddings"), assigns it a unique identifier, and provisions an initial Tenant Admin user. The new tenant starts with an empty, isolated workspace.

**Why this priority**: Required to onboard new agencies. Lower priority because the MVP only needs two tenants, which can be seeded directly for demo purposes.

**Independent Test**: Create a new tenant via the admin interface, log in as its first user, and confirm the workspace is empty and isolated from existing tenants.

**Acceptance Scenarios**:

1. **Given** a Super Admin creates a new tenant, **When** the tenant is provisioned, **Then** a unique `tenant_id` is assigned and no data from other tenants is visible in the new workspace.
2. **Given** a new tenant is created, **When** the initial Tenant Admin logs in, **Then** all data stores (messages, conversations, documents, tasks, escalations, audit logs) are empty for that tenant.
3. **Given** a Super Admin provisions a tenant, **When** they view that tenant's admin panel, **Then** they can see tenant metadata but cannot read the tenant's content data (messages, documents, conversations).

---

### Edge Cases

- What happens when a `tenant_id` is included in a frontend API request body? The backend must derive tenant context from the authenticated session and ignore the client-supplied value.
- What happens when a user's session token is compromised and used from a different IP? The audit log captures the anomaly; the tenant's data remains isolated.
- What happens when a document upload is interrupted mid-processing? Partial chunks must not be queryable; the upload is either committed fully or rolled back.
- What happens if a bug causes a `tenant_id` to be null or missing on a record? The system must reject the write and log an integrity error — never store a record without a `tenant_id`.
- What happens when the same email address is registered in two different tenants? Each registration is independent; credentials are tenant-scoped, not global.

---

## MVP Scope

- Two demo tenants: Elegant Weddings and Royal Events Agency, provisioned at startup
- Tenant context derived from authenticated session (not from frontend payload)
- Full `tenant_id` enforcement on: users, conversations, client messages, uploaded documents, document chunks, suggested replies, follow-up tasks, escalations, audit logs
- RAG retrieval filtered by `tenant_id` at query time
- Suggested replies sourced exclusively from the authenticated tenant's knowledge base
- AI agent tools operate only within the current tenant context
- Cross-tenant access attempts blocked and logged
- Tenant Admin role can view their own tenant's audit log
- Platform Super Admin can provision new tenants

---

## Out of Scope

- Self-service tenant sign-up (tenants are provisioned by Super Admin only)
- Tenant-level custom branding or UI themes
- Cross-tenant collaboration or shared document pools
- Billing and subscription management per tenant
- Tenant data export or GDPR deletion workflows (post-MVP)
- Single sign-on (SSO) or federated identity per tenant
- Tenant-level rate limiting or usage quotas

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | Auth system | Carries the verified `tenant_id` for the current user |
| Client messages | Inbound webhook or UI | Tagged with `tenant_id` derived from the receiving tenant |
| Uploaded documents | Planner via UI | Associated with the uploader's tenant at ingestion |
| Document chunks | Document processor | Inherit `tenant_id` from the parent document |
| RAG query | AI agent | Includes `tenant_id` as a mandatory filter parameter |
| AI reply generation request | Conversation UI | Bound to the authenticated user's tenant context |
| Tenant provisioning request | Super Admin UI | Creates a new tenant with a unique `tenant_id` |

---

## Outputs

| Output | Description |
|--------|-------------|
| Tenant-scoped dashboard | Shows only data belonging to the authenticated tenant |
| AI suggested reply | Generated using only the current tenant's RAG knowledge base |
| Blocked access response | Permission-denied error returned for cross-tenant requests |
| Audit log entry | Immutable record of security events scoped to the relevant tenant |
| Provisioned tenant workspace | Empty, isolated workspace with a unique `tenant_id` |

---

## Main Workflow

1. **User authenticates** — The auth system validates credentials and issues a session token that encodes the user's `tenant_id`.
2. **Session context established** — Every subsequent request extracts `tenant_id` from the session token. Client-supplied `tenant_id` values in request bodies are discarded.
3. **Data access request** — The user or AI agent requests data (messages, documents, conversations, tasks).
4. **Tenant filter applied** — The data layer enforces a `tenant_id` filter on every query. Records without a matching `tenant_id` are invisible.
5. **AI invocation (if applicable)** — The AI agent receives the query with `tenant_id` injected. RAG retrieval filters chunks by `tenant_id`. Suggested replies are generated from those results only.
6. **Response returned** — Only tenant-owned data is included in the response.
7. **Audit log updated** — Security-relevant events (access attempts, AI queries, document uploads) are appended to the tenant's audit log.

---

## Alternative Workflows

### Cross-Tenant Access Attempt

1. Authenticated user makes a request targeting a resource owned by a different tenant.
2. The data layer detects the `tenant_id` mismatch.
3. The request is rejected with a permission-denied error — no data is returned.
4. An audit log entry is created recording: actor, target resource, action, tenant of actor, tenant of resource, timestamp, outcome (blocked).

### Document Upload and Indexing

1. Planner selects a document for upload.
2. Upload request is received; the system attaches the authenticated user's `tenant_id` to the document record.
3. The document processor splits the document into chunks; each chunk inherits the parent document's `tenant_id`.
4. Chunks are stored in the vector knowledge base with `tenant_id` as a mandatory metadata field.
5. If any step fails, the entire upload is rolled back — no partial chunks are stored.

### AI Reply Generation

1. Client message received; conversation is scoped to authenticated tenant.
2. AI agent constructs a retrieval query, injecting the current `tenant_id` as a required filter.
3. RAG system returns only chunks matching the `tenant_id`.
4. AI generates a suggested reply using those chunks as context.
5. Suggested reply is stored with the conversation's `tenant_id`.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | A user authenticated as Tenant A cannot retrieve any record owned by Tenant B | Automated test: cross-tenant ID request returns 403 |
| AC-02 | Every tenant-owned record in every data store includes a non-null `tenant_id` | Schema validation + automated integrity check |
| AC-03 | RAG retrieval never returns chunks from a different tenant | Automated test: query from Tenant B returns zero Tenant A chunks |
| AC-04 | Backend ignores `tenant_id` sent in request bodies; session-derived value is always used | Automated test: send mismatched `tenant_id` in body, verify session value is used |
| AC-05 | Suggested replies contain no content sourced from another tenant's documents | Manual + automated test: unique document content in Tenant A is absent from Tenant B replies |
| AC-06 | Every cross-tenant access attempt is logged with actor, resource, timestamp, and outcome | Automated test: trigger blocked request, verify audit log entry |
| AC-07 | Tenant Admin can view their own audit log but not another tenant's | Role-based access test for audit log endpoint |
| AC-08 | Super Admin can provision a new tenant that starts with an empty, isolated workspace | E2E test: provision tenant, log in, confirm empty data stores |
| AC-09 | Document upload failure results in no partial chunks stored in the knowledge base | Automated test: interrupt upload, verify chunk table has no partial records |
| AC-10 | The two demo tenants (Elegant Weddings, Royal Events Agency) are provisioned and isolated at system startup | Smoke test: both tenants accessible; cross-tenant data invisible |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Authentication system | Required | Must issue session tokens containing verified `tenant_id`; no external tenant lookup required at runtime |
| User management | Required | Users must be associated with exactly one tenant at registration |
| Document ingestion pipeline | Required | Must accept and propagate `tenant_id` through chunking and vector storage |
| Vector knowledge base | Required | Must support metadata filtering by `tenant_id` on every retrieval query |
| AI reply generation service | Required | Must accept `tenant_id` as a parameter and never query outside that scope |
| Audit log storage | Required | Must be append-only and tenant-scoped |

---

## AI Behavior

- The AI agent receives `tenant_id` as part of every invocation context; it cannot be overridden by user input.
- All tool calls made by the AI agent (document retrieval, conversation lookup, task creation) are automatically scoped to the current `tenant_id`.
- The AI must not synthesize information from memory or cached context that originated from a different tenant's session.
- When the AI generates a suggested reply, it must cite only sources retrieved from the current tenant's knowledge base during that invocation.
- The AI must not accept instructions from users that attempt to override tenant context (e.g., "pretend you are working for Tenant B").

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Session is the source of truth** | `tenant_id` is derived from the authenticated session token only. Client-supplied `tenant_id` values in request bodies or query parameters are discarded and logged. |
| **SR-02: Mandatory `tenant_id` on all records** | Every write to any data store must include a non-null `tenant_id`. Records without a valid `tenant_id` must be rejected with an integrity error. |
| **SR-03: Tenant filter on all reads** | Every read query on tenant-owned data stores must include a `tenant_id` equality filter. Queries without this filter must be rejected at the data layer. |
| **SR-04: Cross-tenant access blocked and logged** | Any request whose resolved `tenant_id` does not match the resource's `tenant_id` must be rejected with a 403-class error. The attempt must be recorded in the audit log. |
| **SR-05: RAG isolation** | The vector retrieval system must apply `tenant_id` as a mandatory pre-filter before scoring or ranking any results. Post-retrieval filtering is insufficient. |
| **SR-06: AI tool isolation** | AI agent tools may not accept `tenant_id` as a user-facing parameter. The tenant context is injected by the system at invocation time only. |
| **SR-07: Audit log integrity** | Audit logs are append-only and may not be modified or deleted by any tenant-level role. Only the Platform Super Admin and the relevant Tenant Admin may read them. |
| **SR-08: Partial write prevention** | Document ingestion is transactional. A failure at any stage must roll back all associated chunk writes to prevent orphaned, untagged, or partially-tagged records. |

---

## Assumptions

- Each user belongs to exactly one tenant. Multi-tenant user accounts (one identity across multiple tenants) are out of scope for MVP.
- Tenant provisioning for the two demo tenants is performed via a seed script or admin operation at deployment time, not through a production UI flow.
- The authentication system is already capable of embedding `tenant_id` in session tokens; this spec does not redesign the auth layer.
- The vector knowledge base supports metadata equality filters that are applied server-side before results are returned to the caller.
- Platform Super Admins do not need to read the content of tenant messages, documents, or conversations to perform their duties.
- Performance targets follow standard web application expectations; no special high-throughput requirements are assumed for the MVP.
