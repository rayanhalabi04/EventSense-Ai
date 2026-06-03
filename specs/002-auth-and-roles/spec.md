# Feature Specification: Authentication and Roles

**Feature Branch**: `002-auth-and-roles`

**Created**: 2026-06-03

**Status**: Draft

**Connects to**: [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)

**Input**: User description: "Authentication and Roles — defines how users log in, how their tenant context is established, and how staff, manager, and platform admin roles are enforced across EventSense AI."

---

## Goal

Establish a secure, tenant-aware login system for EventSense AI. When a user logs in with their email and password, the system issues a signed token that encodes their identity, their tenant, and their role. Every subsequent request is authorized based solely on that token — the backend never trusts identity or tenant information supplied directly by the client.

The three MVP roles — **Staff**, **Manager**, and **Platform Admin** — define a clear permission boundary: Staff handles day-to-day client interactions; Managers oversee documents, escalations, and audit visibility; Platform Admins provision tenants but cannot read tenant content.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner or agent within a tenant. Handles inbound messages, reads AI-generated reply suggestions, creates follow-up tasks, escalates cases, and marks conversations as resolved. Cannot upload or manage knowledge-base documents. |
| **Manager** | A senior planner or agency manager within a tenant. Has all Staff capabilities plus the ability to upload and manage documents, review and resolve escalations, view the tenant's audit log, and manage high-risk or sensitive conversations. |
| **Platform Admin** | An internal operator of EventSense AI. Can provision and deactivate demo tenants and their initial admin users. Cannot read any tenant's messages, documents, or conversations unless explicitly granted by a backend rule. |

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

A Staff user attempts to access a manager-only feature (such as the audit log or document management). The system blocks the request and returns a clear permission-denied response. A Manager attempting the same action succeeds. Neither user can elevate their own role.

**Why this priority**: Role enforcement is the second pillar of authorization after authentication. Without it, role definitions are cosmetic and any user could access any feature.

**Independent Test**: Authenticated as Staff, request a route that requires Manager role — expect 403. Authenticated as Manager, request the same route — expect success. Verify no client-side action can change the role claim in the token.

**Acceptance Scenarios**:

1. **Given** a Staff user with a valid token, **When** they request a Manager-only route (e.g., document upload, audit log), **Then** the system returns 403 Forbidden.
2. **Given** a Manager user with a valid token, **When** they request a Staff-level route (e.g., view conversations), **Then** the system processes the request normally.
3. **Given** a Manager user with a valid token, **When** they request a Manager-level route (e.g., view audit log), **Then** the system processes the request normally.
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

### User Story 4 — Manager Access to Audit Log and Escalations (Priority: P2)

A manager at Elegant Weddings logs in and reviews the audit log for recent security events in their agency. They also review open escalations and resolve one. A Staff user at the same agency who attempts the same views is blocked with 403.

**Why this priority**: The audit log and escalation review are management tools. Restricting them to Manager role ensures only accountable principals can inspect security history and close sensitive cases.

**Independent Test**: Authenticated as Manager, `GET /audit-logs` and `GET /escalations` succeed. Authenticated as Staff at the same tenant, both return 403.

**Acceptance Scenarios**:

1. **Given** a Manager at tenant X, **When** they access the audit log, **Then** they see only tenant X's audit events.
2. **Given** a Staff user at tenant X, **When** they attempt to access the audit log, **Then** they receive 403 Forbidden.
3. **Given** a Manager at tenant X, **When** they resolve an escalation, **Then** the resolution is recorded and the escalation status updates.
4. **Given** a Manager at tenant X, **When** they attempt to access tenant Y's audit log, **Then** they receive 403 Forbidden (cross-tenant blocking from Spec 001 still applies).

---

### User Story 5 — Platform Admin Provisions a Tenant (Priority: P3)

A Platform Admin logs in and creates a new tenant with an initial Manager user. The Platform Admin can see the list of tenants and their status, but cannot open any tenant's conversations, documents, or messages.

**Why this priority**: Required to onboard new agencies. Lower priority because the two demo tenants can be seeded directly for the MVP launch; a provisioning UI is needed for the first real onboarding.

**Independent Test**: Authenticate as Platform Admin, provision a new tenant, verify it appears in the tenant list. Then attempt to access a protected tenant content route (conversations, documents) — expect 403.

**Acceptance Scenarios**:

1. **Given** a Platform Admin, **When** they provision a new tenant with a valid name and initial admin email, **Then** the tenant is created and an initial Manager user is provisioned.
2. **Given** a Platform Admin, **When** they attempt to access `GET /conversations` for any tenant, **Then** they receive 403 Forbidden.
3. **Given** a Platform Admin, **When** they deactivate a tenant, **Then** all users in that tenant receive 401 on subsequent requests (inactive tenant check at login).
4. **Given** a non-Platform-Admin user (Staff or Manager), **When** they attempt to access a Platform Admin route, **Then** they receive 403 Forbidden.

---

### Edge Cases

- What happens when a user submits the correct email but wrong password? The system returns 401 with a generic message ("Invalid credentials") — no indication of which field was wrong, to prevent username enumeration.
- What happens when a user account is deactivated while they have an active token? The token remains valid until expiry (acceptable for MVP); deactivation takes full effect at next login or token refresh.
- What happens when a tenant is deactivated? All login attempts for users of that tenant are rejected with 401.
- What happens when the same email is registered in two different tenants? Each registration is independent. The login flow must identify the tenant context either from a tenant slug in the login form or by requiring the user to select their tenant when the email matches multiple accounts.
- What happens if a Staff user's token encodes an incorrect role due to a system bug? The incorrect role is honoured (token is authoritative) — the fix is to re-issue a correct token, not to override the claim server-side.

---

## MVP Scope

- Email and password login returning a signed token with `user_id`, `tenant_id`, and `role`
- Three roles: Staff, Manager, Platform Admin
- Staff capabilities: view messages, read AI suggestions, create tasks, escalate cases, mark conversations resolved
- Manager capabilities: all Staff capabilities plus document upload/management, escalation review/resolution, audit log access
- Platform Admin capabilities: tenant provisioning/deactivation, tenant list view — no tenant content access
- 401 for unauthenticated or expired token requests
- 403 for insufficient-role requests, with audit log entry written
- Token refresh endpoint (extends session without re-entering password)
- Audit logging for: login success, login failure, role violation, token expiry event
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

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Email address | Login form | User-supplied; used to look up the account |
| Password | Login form | User-supplied; validated against the stored credential |
| Existing token | Request header | Presented on every protected request for validation |
| Tenant slug or identifier | Login form or subdomain | Used to resolve tenant context when email exists in multiple tenants |
| Tenant provisioning request | Platform Admin UI | Name, slug, initial Manager email and password |

---

## Outputs

| Output | Description |
|--------|-------------|
| Signed token | Issued on successful login; contains `user_id`, `tenant_id`, `role`, and expiry |
| Refreshed token | Issued by the refresh endpoint; same claims, extended expiry |
| 401 Unauthorized | Returned when credentials are invalid, token is missing, or token has expired |
| 403 Forbidden | Returned when the authenticated role is insufficient for the requested action |
| Audit log entry | Written for login success, login failure, role violation, and token expiry |
| Provisioned tenant + Manager user | Created by Platform Admin provisioning; returns new `tenant_id` and `user_id` |

---

## Main Workflow

1. **User navigates to the login screen** — The application presents an email/password form. If the platform uses tenant subdomains, the tenant context is implied; otherwise a tenant identifier field is shown.
2. **Credentials submitted** — The user submits email and password.
3. **Backend validates credentials** — The backend looks up the user by email within the resolved tenant. It verifies the password against the securely stored credential. If either fails, a 401 is returned and a failed-login audit event is written.
4. **Tenant and user status checked** — If the tenant is inactive or the user account is inactive, a 401 is returned.
5. **Token issued** — A signed token is generated containing `user_id`, `tenant_id`, and `role`. The token includes a standard expiry.
6. **Login audit event written** — A successful-login event is appended to the audit log.
7. **Frontend receives token** — The frontend stores the token securely and attaches it to all subsequent requests.
8. **Protected request processed** — On each request, the backend extracts and validates the token, constructs the tenant context from its claims, and checks whether the user's role is sufficient for the requested action.
9. **Response returned** — If all checks pass, the request is processed. If the role is insufficient, 403 is returned and a role-violation audit event is written.

---

## Alternative Workflows

### Login Failure — Wrong Credentials

1. User submits email and password.
2. Backend cannot find the user or password does not match.
3. 401 is returned with generic message: "Invalid credentials."
4. A failed-login audit event is written (tenant, email, timestamp, IP address, outcome: blocked).
5. No token is issued.

### Login Failure — Inactive Account or Tenant

1. User submits valid credentials.
2. Backend finds the user and validates the password, but the user or their tenant is marked inactive.
3. 401 is returned.
4. A failed-login audit event is written with reason: inactive.

### Expired Token

1. User presents a token that has passed its expiry.
2. Backend rejects the token with 401.
3. Frontend detects 401 and redirects the user to the login screen.
4. User re-authenticates; a fresh token is issued.

### Token Refresh

1. Before the token expires, the frontend calls the refresh endpoint with the current valid token.
2. Backend validates the token (must be valid and not yet expired).
3. A new token is issued with the same claims and a refreshed expiry.
4. The old token is superseded by the new one (not revoked, for MVP simplicity).

### Role Violation

1. A Staff user calls a Manager-only endpoint.
2. Backend validates the token successfully but detects the role is insufficient.
3. 403 is returned with error code `INSUFFICIENT_ROLE`.
4. A role-violation audit event is written: actor, endpoint, required role, actual role, timestamp.

### Platform Admin Content Access Attempt

1. Platform Admin calls a tenant content endpoint (e.g., `GET /conversations`).
2. Backend validates the token; role is `platform_admin`.
3. The content route is annotated as requiring `staff` or `manager` role.
4. 403 is returned.
5. An audit event is written.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Successful login with valid credentials returns a token containing correct `user_id`, `tenant_id`, and `role` claims | Decode token from login response; assert all three claims are present and correct |
| AC-02 | Invalid credentials (wrong password or unknown email) return 401 with no token | Submit bad credentials; assert 401 and no token in response |
| AC-03 | An inactive user cannot log in even with correct credentials | Deactivate user; attempt login; assert 401 |
| AC-04 | An inactive tenant blocks all logins for its users | Deactivate tenant; attempt login as any user; assert 401 |
| AC-05 | Staff role cannot access Manager-only routes; receives 403 | Authenticated as Staff, request audit log endpoint; assert 403 |
| AC-06 | Manager role can access all Staff-level and Manager-level routes | Authenticated as Manager, request Staff and Manager routes; assert 200 |
| AC-07 | Platform Admin cannot access tenant content routes; receives 403 | Authenticated as Platform Admin, request `GET /conversations`; assert 403 |
| AC-08 | An expired token returns 401 on any protected route | Advance clock past expiry; present token; assert 401 |
| AC-09 | All login failures are audit-logged with email, tenant, timestamp, IP, and outcome | Trigger login failure; query audit log; assert matching entry |
| AC-10 | All role violations are audit-logged with actor, endpoint, required role, actual role, and timestamp | Trigger role violation; query audit log; assert matching entry |
| AC-11 | Token refresh before expiry returns a new token with the same claims and a later expiry | Call refresh with valid token; compare claims and expiry |
| AC-12 | The backend never uses a `tenant_id` or `role` value supplied in the request body or query string | Submit login with extra `tenant_id` body field; verify it is ignored and session-derived value is used |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Provides the `users` table (with `tenant_id`, `role`, `hashed_password`, `is_active`), `tenants` table (with `is_active`), and `audit_logs` table. This spec adds auth behaviour on top of that schema — it does not redefine it. |
| Tenant resolution mechanism | Required | The login flow must be able to identify which tenant a user belongs to. Assumes tenant slug is present in the login request (subdomain or form field). |
| Secure credential storage | Required | Passwords must be stored as one-way hashes. This spec assumes that mechanism is in place when the `users` table is seeded. |
| Audit log service (Spec 001) | Required | Auth events are written to the same `audit_logs` table via the same append-only service defined in Spec 001. |

---

## AI Behavior

- The AI agent that generates reply suggestions or retrieves document context operates within a session established by this feature. It inherits the `tenant_id` and `role` from the authenticated user's token.
- The AI agent's tools are restricted by role: Staff-level sessions can trigger AI reply suggestions; Manager-level sessions can additionally trigger document indexing or re-processing.
- The AI agent cannot modify, inspect, or override the token claims. All tenant and role context is injected by the system at invocation time based on the authenticated session.
- If the AI agent is called in an unauthenticated or expired-session context, the invocation is rejected with the same 401 response as any other protected route.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Credentials never returned** | The login response contains only the signed token. Passwords and credential hashes are never returned in any API response. |
| **SR-02: Token is the authority** | The backend derives `user_id`, `tenant_id`, and `role` exclusively from the validated token. Request bodies and query parameters claiming to carry these values are discarded and logged. |
| **SR-03: Generic error messages** | Login failure responses never indicate whether the email exists or the password was wrong. The message is always "Invalid credentials" to prevent account enumeration. |
| **SR-04: Expiry is enforced** | Every token has an expiry embedded by the issuing system. The backend validates expiry on every request. There is no mechanism to issue a non-expiring token. |
| **SR-05: Failed logins are audit-logged** | Every failed login attempt is written to the audit log with: email used, tenant (if resolvable), IP address, timestamp, and outcome (blocked). This enables detection of brute-force patterns. |
| **SR-06: Role violations are audit-logged** | Every 403 response due to insufficient role is written to the audit log with: actor `user_id`, endpoint, required role, actual role, and timestamp. |
| **SR-07: Platform Admin content block** | Routes that serve tenant content (messages, documents, conversations, suggested replies, tasks, escalations) must require `staff` or `manager` role. Platform Admin role alone is insufficient for these routes. |
| **SR-08: Inactive checks at login** | An inactive user or an inactive tenant is always rejected at login time, regardless of whether the password is correct. The distinction between "wrong password" and "inactive account" is not revealed to the caller. |

---

## Assumptions

- Each user belongs to exactly one tenant in the MVP. A future multi-tenant-per-user model is out of scope.
- The login form includes a tenant identifier (subdomain or slug field) so the backend can resolve the correct tenant when the email is not globally unique.
- Token storage on the client is handled by the frontend using best-practice security (e.g., httpOnly cookies or secure in-memory storage). This spec does not dictate the storage mechanism.
- Token lifetime defaults to 60 minutes for the session token and 24 hours for a refresh window. These are configurable and represent standard security defaults.
- Password reset via email is deferred to a post-MVP feature. For the MVP, demo tenant passwords are set during seeding and changed by a Manager or Platform Admin through a secure admin workflow.
- Audit log writes for auth events use the same `AuditService` defined in Spec 001, ensuring consistent append-only semantics.
- Rate limiting on the login endpoint is assumed to be provided by infrastructure (reverse proxy, API gateway) rather than implemented in application code for the MVP.
