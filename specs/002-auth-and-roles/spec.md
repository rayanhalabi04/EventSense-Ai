# Feature Specification: Authentication and Roles

**Feature Branch**: `002-auth-and-roles`

**Created**: 2026-06-03

**Status**: Draft

**Connects to**: [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)

**Input**: User description: "Authentication and Roles — defines how users log in, how their tenant context is established, and how staff, manager, and platform admin roles are enforced across EventSense AI."

---

## Goal

Establish a secure, tenant-aware login system for EventSense AI. When a user logs in with their email and password, the system issues a signed token that encodes their identity, their tenant, and their role. Every subsequent request is authorized based solely on that token — the backend never trusts identity or tenant information supplied directly by the client.

The three MVP roles — **Staff**, **Manager**, and **Platform Admin** — define a clear permission boundary for current and future routes. Staff and Manager are tenant users. Platform Admin is only for platform/demo administration and cannot read tenant content by default.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner or agent within a tenant. Can access tenant content routes intended for day-to-day event operations once those routes exist. |
| **Manager** | A senior planner or agency manager within a tenant. Inherits Staff-level access and is the role policy target for future manager-only tools such as document management, escalation review, and audit-log review. |
| **Platform Admin** | An internal operator of EventSense AI for platform/demo administration. Cannot read any tenant's messages, documents, conversations, tasks, escalations, audit logs, or AI outputs by default. |

---

## User Stories

### User Story 1 — Staff Login and Authenticated Session (Priority: P1)

A staff planner navigates to the EventSense AI login page, enters their email and password, and is taken directly to their tenant's dashboard. Their token encodes their identity, their tenant, and their Staff role. Unauthenticated access to any dashboard page redirects to the login screen.

**Why this priority**: Login is the gateway to every feature in the system. Without it, no tenant-scoped data can be safely served. All other user stories in this and dependent features depend on a valid, role-bearing session.

**Independent Test**: Can be fully tested by submitting valid Staff credentials and verifying the response contains a token with the correct `user_id`, `tenant_id`, and `role=staff` claims. Then verify a protected route responds normally with that token and returns 401 without it.

**Acceptance Scenarios**:

1. **Given** a Staff user with valid credentials, **When** they submit their email and password, **Then** the system returns a signed token containing their `user_id`, `tenant_id`, and `role`.
2. **Given** a valid token, **When** a Staff user requests a protected route, **Then** the system processes the request using the tenant and role from the token.
3. **Given** no token or an invalid token, **When** any user attempts to access a protected route, **Then** the system returns a 401 Unauthorized response.
4. **Given** a token that has expired, **When** it is presented to a protected route, **Then** the system returns 401 and the frontend redirects the user to the login screen.

---

### User Story 2 — Role-Based Access Enforcement (Priority: P1)

A Staff user attempts to access a route protected by a Manager-only role guard. The system blocks the request and returns a clear permission-denied response. A Manager attempting the same protected route succeeds. Neither user can elevate their own role.

**Why this priority**: Role enforcement is the second pillar of authorization after authentication. Without it, role definitions are cosmetic and any user could access any feature.

**Independent Test**: Authenticated as Staff, request a route that requires Manager role — expect 403. Authenticated as Manager, request the same route — expect success. Verify no client-side action can change the role claim in the token.

**Acceptance Scenarios**:

1. **Given** a Staff user with a valid token, **When** they request a currently implemented Manager-only route or test route, **Then** the system returns 403 Forbidden.
2. **Given** a Manager user with a valid token, **When** they request a Staff-level route (e.g., view conversations), **Then** the system processes the request normally.
3. **Given** a Manager user with a valid token, **When** they request the same Manager-only route or test route, **Then** the system processes the request normally.
4. **Given** any user, **When** they attempt to modify the role claim in their token, **Then** the system rejects the token as invalid and returns 401.

---

### User Story 3 — Token Expiry and Re-authentication (Priority: P2)

A staff planner has been working in the dashboard for several hours. Their session token expires. The next action they take automatically redirects them to the login screen, and after re-entering credentials they are returned to where they left off.

**Why this priority**: Session expiry is a standard security control. Tokens that never expire are a significant credential theft risk.

**Independent Test**: Issue a token, advance the clock past the expiry threshold, present the expired token to a protected route — expect 401. Re-authenticate with valid credentials — expect a fresh valid token.

**Acceptance Scenarios**:

1. **Given** a token has passed its expiry time, **When** it is presented to any protected route, **Then** the system returns 401 and does not process the request.
2. **Given** a user is redirected to login after expiry, **When** they re-enter valid credentials, **Then** they receive a fresh token and are returned to the application.
3. **Given** a valid, non-expired token, **When** the user calls the token refresh endpoint before expiry, **Then** a new token with a refreshed expiry is returned without requiring password re-entry.

---

### User Story 4 — Manager Role Policy for Future Tools (Priority: P2)

A manager at Elegant Weddings logs in and can pass Manager-only route guards. A Staff user at the same agency who attempts the same Manager-only protected route is blocked with 403. This story defines role policy for later documents, escalations, audit logs, and other manager-only tools; it does not implement those workflows in Spec 002.

**Why this priority**: Later manager-only tools must have a clear role policy before they are implemented. Restricting those future routes to Manager ensures only accountable tenant users can access sensitive management workflows.

**Independent Test**: Authenticated as Manager, call a currently implemented Manager-only route or test route — expect success. Authenticated as Staff at the same tenant, call the same route — expect 403.

**Acceptance Scenarios**:

1. **Given** a Manager at tenant X, **When** they request a Manager-only route in the current codebase, **Then** the role guard allows the request.
2. **Given** a Staff user at tenant X, **When** they request the same Manager-only route, **Then** they receive 403 Forbidden.
3. **Given** a future document, escalation, audit-log, or RAG-management route is created, **When** its route contract is written, **Then** it must explicitly apply the Manager-only policy defined here.
4. **Given** a Manager at tenant X, **When** they request any tenant-scoped future manager route, **Then** cross-tenant blocking from Spec 001 still applies.

---

### User Story 5 — Platform Admin Boundary (Priority: P3)

A Platform Admin logs in and can access platform/demo administration routes that already exist, such as tenant metadata listing from Spec 001. The Platform Admin cannot open any tenant's conversations, documents, messages, tasks, escalations, audit logs, or AI outputs.

**Why this priority**: Platform Admin is powerful enough to manage demo/platform metadata, so the content-access boundary must be explicit before tenant content routes are implemented.

**Independent Test**: Authenticate as Platform Admin, access an existing platform metadata route — expect success. Then attempt to access a protected tenant content route or test route — expect 403.

**Acceptance Scenarios**:

1. **Given** a Platform Admin, **When** they request an existing platform metadata/admin route, **Then** the role guard allows the request.
2. **Given** a Platform Admin, **When** they attempt to access `GET /conversations` for any tenant, **Then** they receive 403 Forbidden.
3. **Given** a Platform Admin, **When** they attempt to access a future tenant content route such as documents, tasks, escalations, audit logs, RAG, or suggested replies, **Then** the route policy must block access by default.
4. **Given** a non-Platform-Admin user (Staff or Manager), **When** they attempt to access a Platform Admin route, **Then** they receive 403 Forbidden.

---

### Edge Cases

- What happens when a user submits the correct email but wrong password? The system returns 401 with a generic message ("Invalid credentials") — no indication of which field was wrong, to prevent username enumeration.
- What happens when a user account is deactivated while they have an active token? The token remains valid until expiry (acceptable for MVP); deactivation takes full effect at next login or token refresh because refresh re-checks active user and tenant state.
- What happens when a tenant is deactivated? All login attempts for users of that tenant are rejected with 401.
- What happens when the same email is registered in two different tenants? Each registration is independent. The login flow must identify the tenant context either from a tenant slug in the login form or by requiring the user to select their tenant when the email matches multiple accounts.
- What happens if a Staff user's token encodes an incorrect role due to a system bug? The incorrect role is honoured (token is authoritative) — the fix is to re-issue a correct token, not to override the claim server-side.

---

## MVP Scope

- Email and password login returning a signed token with `user_id`, `tenant_id`, and `role`
- Three roles: Staff, Manager, Platform Admin
- Staff route policy for day-to-day tenant content routes created by current or later specs
- Manager route policy for future manager-only tools such as document management, escalation review, audit-log review, and RAG-management routes
- Platform Admin route policy for platform/demo administration routes — no tenant content access by default
- 401 for unauthenticated or expired token requests
- 403 for insufficient-role requests, with an audit event hook emitted for future audit infrastructure
- Token refresh endpoint (extends session without re-entering password)
- Audit event names for future audit integration: login success, login failure, role violation, token refresh, logout
- Inactive user and inactive tenant blocks at login
- The backend derives all authorization context from the token — never from client-supplied values

---

## Out of Scope

- Social login / OAuth2 / SSO (Google, Microsoft, etc.)
- Multi-factor authentication
- Password reset via email link (post-MVP)
- Magic link or passwordless login
- Per-user permission overrides (granular RBAC beyond the three roles)
- Session management UI (active sessions list, remote logout)
- Role assignment self-service by users (roles are set at provisioning or by Platform Admin)
- Audit log for routine data reads (only security-relevant events are logged)
- Implementing document upload, RAG, suggested replies, task workflows, escalation workflows, guardrails, evaluation, or audit-log persistence
- Platform tenant provisioning/deactivation APIs beyond existing Spec 001 demo/platform metadata support

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Email address | Login form | User-supplied; used to look up the account |
| Password | Login form | User-supplied; validated against the stored credential |
| Existing token | Request header | Presented on every protected request for validation |
| Tenant slug or identifier | Login form or subdomain | Used to resolve tenant context when email exists in multiple tenants |

---

## Outputs

| Output | Description |
|--------|-------------|
| Signed token | Issued on successful login; contains `user_id`, `tenant_id`, `role`, and expiry |
| Refreshed token | Issued by the refresh endpoint; same claims, extended expiry |
| 401 Unauthorized | Returned when credentials are invalid, token is missing, or token has expired |
| 403 Forbidden | Returned when the authenticated role is insufficient for the requested action |
| Audit event hook | Named for login success, login failure, role violation, token refresh, and logout; persistence is deferred to the later audit-log feature |

---

## Main Workflow

1. **User navigates to the login screen** — The application presents an email/password form. If the platform uses tenant subdomains, the tenant context is implied; otherwise a tenant identifier field is shown.
2. **Credentials submitted** — The user submits email and password.
3. **Backend validates credentials** — The backend looks up the user by email within the resolved tenant. It verifies the password against the securely stored credential. If either fails, a 401 is returned and a failed-login audit event hook is emitted for future audit infrastructure.
4. **Tenant and user status checked** — If the tenant is inactive or the user account is inactive, a 401 is returned.
5. **Token issued** — A signed token is generated containing `user_id`, `tenant_id`, and `role`. The token includes a standard expiry.
6. **Login audit event hook emitted** — A successful-login event hook is emitted for future audit infrastructure.
7. **Frontend receives token** — The frontend stores the token securely and attaches it to all subsequent requests.
8. **Protected request processed** — On each request, the backend extracts and validates the token, constructs the tenant context from its claims, and checks whether the user's role is sufficient for the requested action.
9. **Response returned** — If all checks pass, the request is processed. If the role is insufficient, 403 is returned and a role-violation audit event hook is emitted for future audit infrastructure.

---

## Alternative Workflows

### Login Failure — Wrong Credentials

1. User submits email and password.
2. Backend cannot find the user or password does not match.
3. 401 is returned with generic message: "Invalid credentials."
4. A failed-login audit event hook is emitted for future audit infrastructure (tenant, email, timestamp, IP address, outcome: blocked).
5. No token is issued.

### Login Failure — Inactive Account or Tenant

1. User submits valid credentials.
2. Backend finds the user and validates the password, but the user or their tenant is marked inactive.
3. 401 is returned.
4. A failed-login audit event hook is emitted with reason: inactive.

### Expired Token

1. User presents a token that has passed its expiry.
2. Backend rejects the token with 401.
3. Frontend detects 401 and redirects the user to the login screen.
4. User re-authenticates; a fresh token is issued.

### Token Refresh

1. Before the token expires, the frontend calls the refresh endpoint with the current valid token.
2. Backend validates the token (must be valid and not yet expired).
3. Backend re-checks that the user and tenant are still active.
4. A new token is issued with the same user/tenant/role claims and a refreshed expiry.
5. The old token is superseded by the new one (not revoked, for MVP simplicity).

### Role Violation

1. A Staff user calls a Manager-only endpoint.
2. Backend validates the token successfully but detects the role is insufficient.
3. 403 is returned with error code `INSUFFICIENT_ROLE`.
4. A role-violation audit event hook is emitted: actor, endpoint, required role, actual role, timestamp.

### Platform Admin Content Access Attempt

1. Platform Admin calls a tenant content endpoint (e.g., `GET /conversations`).
2. Backend validates the token; role is `platform_admin`.
3. The content route is annotated as requiring `staff` or `manager` role.
4. 403 is returned.
5. A platform-admin content-access audit event hook is emitted for future audit infrastructure.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Successful login with valid credentials returns a token containing correct `user_id`, `tenant_id`, and `role` claims | Decode token from login response; assert all three claims are present and correct |
| AC-02 | Invalid credentials (wrong password or unknown email) return 401 with no token | Submit bad credentials; assert 401 and no token in response |
| AC-03 | An inactive user cannot log in even with correct credentials | Deactivate user; attempt login; assert 401 |
| AC-04 | An inactive tenant blocks all logins for its users | Deactivate tenant; attempt login as any user; assert 401 |
| AC-05 | Staff role cannot access Manager-only routes; receives 403 | Authenticated as Staff, request a current Manager-only route or test route; assert 403 |
| AC-06 | Manager role can access all Staff-level and Manager-level routes | Authenticated as Manager, request Staff and Manager routes; assert 200 |
| AC-07 | Platform Admin cannot access tenant content routes; receives 403 | Authenticated as Platform Admin, request `GET /conversations`; assert 403 |
| AC-08 | An expired token returns 401 on any protected route | Advance clock past expiry; present token; assert 401 |
| AC-09 | Login failures emit/record a `login_failure` event with email, tenant slug, IP, and outcome when audit infrastructure exists | Trigger login failure; assert event call/record without logging password |
| AC-10 | Role violations emit/record an `insufficient_role` event with actor, endpoint, required role, actual role, and timestamp when audit infrastructure exists | Trigger role violation; assert event call/record |
| AC-11 | Token refresh before expiry returns a new token with the same claims and a later expiry after re-checking active user and tenant state | Call refresh with valid token; compare claims/expiry; deactivate user or tenant and verify refresh returns 401 |
| AC-12 | The backend never uses a `tenant_id` or `role` value supplied in the request body or query string | Submit login with extra `tenant_id` body field; verify it is ignored and session-derived value is used |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Provides the `users` table (with `tenant_id`, `role`, `hashed_password`, `is_active`) and `tenants` table (with `is_active`). This spec adds auth behaviour on top of that schema — it does not redefine it. |
| Tenant resolution mechanism | Required | The login flow must be able to identify which tenant a user belongs to. Assumes tenant slug is present in the login request (subdomain or form field). |
| Secure credential storage | Required | Passwords must be stored as one-way hashes. This spec assumes that mechanism is in place when the `users` table is seeded. |
| Audit log feature | Future | Auth event names are defined here; persistence is deferred to the later audit-log feature. |

---

## AI Behavior

- Future AI tools for reply suggestions, document retrieval, RAG, and risk workflows operate within a session established by this feature. They inherit the `tenant_id` and `role` from the authenticated user's token.
- Future AI tools are restricted by role policy from this feature. Spec 002 does not implement those AI workflows.
- The AI agent cannot modify, inspect, or override the token claims. All tenant and role context is injected by the system at invocation time based on the authenticated session.
- If the AI agent is called in an unauthenticated or expired-session context, the invocation is rejected with the same 401 response as any other protected route.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Credentials never returned** | The login response contains only the signed token. Passwords and credential hashes are never returned in any API response. |
| **SR-02: Token is the authority** | The backend derives `user_id`, `tenant_id`, and `role` exclusively from the validated token. Request bodies and query parameters claiming to carry these values are ignored and may emit a future audit event. |
| **SR-03: Generic error messages** | Login failure responses never indicate whether the email exists or the password was wrong. The message is always "Invalid credentials" to prevent account enumeration. |
| **SR-04: Expiry is enforced** | Every token has an expiry embedded by the issuing system. The backend validates expiry on every request. There is no mechanism to issue a non-expiring token. |
| **SR-05: Failed login event hook** | Every failed login attempt emits a future-audit event hook with: email used, tenant (if resolvable), IP address, timestamp, and outcome (blocked). Persistence happens only when the later audit-log feature exists. |
| **SR-06: Role violation event hook** | Every 403 response due to insufficient role emits a future-audit event hook with: actor `user_id`, endpoint, required role, actual role, and timestamp. Persistence happens only when the later audit-log feature exists. |
| **SR-07: Platform Admin content block** | Routes that serve tenant content (messages, documents, conversations, suggested replies, tasks, escalations) must require `staff` or `manager` role. Platform Admin role alone is insufficient for these routes. |
| **SR-08: Inactive checks at login** | An inactive user or an inactive tenant is always rejected at login time, regardless of whether the password is correct. The distinction between "wrong password" and "inactive account" is not revealed to the caller. |

---

## Assumptions

- Each user belongs to exactly one tenant in the MVP. A future multi-tenant-per-user model is out of scope.
- The login form includes a tenant identifier (subdomain or slug field) so the backend can resolve the correct tenant when the email is not globally unique.
- Token storage on the client is handled by the frontend using best-practice security (e.g., httpOnly cookies or secure in-memory storage). This spec does not dictate the storage mechanism.
- Token lifetime defaults to 60 minutes for the session token. `/auth/refresh` only accepts a still-valid access token and does not introduce a separate refresh-token window in the MVP.
- Password reset via email is deferred to a post-MVP feature. For the MVP, demo tenant passwords are set during seeding and changed by a Manager or Platform Admin through a secure admin workflow.
- Auth event names are defined here for later audit-log integration. Persisting those events is deferred to the dedicated audit-log feature.
- Rate limiting on the login endpoint is assumed to be provided by infrastructure (reverse proxy, API gateway) rather than implemented in application code for the MVP.
