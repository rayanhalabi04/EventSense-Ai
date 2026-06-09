# Feature Specification: WhatsApp-Style Message Simulator

**Feature Branch**: `003-message-simulator`

**Created**: 2026-06-03

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)

**Input**: User description: "WhatsApp-Style Message Simulator — allows demo users and staff to inject realistic inbound client messages into a tenant workspace without using the real WhatsApp Business API."

---

## Goal

Provide a controlled simulator that lets staff and demo users inject realistic inbound client messages into EventSense AI as if they had arrived through WhatsApp. This unlocks the full demo and development workflow — allowing AI reply suggestions, inbox views, task creation, and escalation handling to be tested and demonstrated without any live messaging infrastructure.

Every simulated message is fully tenant-isolated, auditable, and indistinguishable in structure from a real inbound message. When the real WhatsApp integration is built in a future feature, it will write messages in the same format the simulator already uses.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner within a tenant who uses the simulator to inject test or demo messages on behalf of a client — for example, to demonstrate the AI reply flow to a prospect or to test a new edge-case scenario. |
| **Manager** | A senior planner who may use the simulator to seed realistic data for training, onboarding new staff, or running internal demos. Has the same simulator access as Staff. |
| **Demo Operator** | Either role acting during a product demonstration. Uses quick-inject preset messages to show the full pipeline without needing a real client. |

---

## User Stories

### User Story 1 — Inject a New Inbound Message (Priority: P1)

A staff planner opens the message simulator, selects or creates a client (name and optional contact), types a message, and submits it. The message is created as an inbound record in the tenant's conversation for that client and immediately appears in the inbox view.

**Why this priority**: This is the core capability. Everything else — AI replies, task creation, escalation — requires an inbound message to exist first. Without this story, no downstream feature can be demonstrated or tested.

**Independent Test**: Submit a simulated message for a client name that does not yet have a conversation. Verify that: (1) a new conversation is created for that client within the authenticated tenant; (2) the message appears in the conversation with `direction=inbound`; (3) the message does not appear in any other tenant's inbox.

**Acceptance Scenarios**:

1. **Given** an authenticated Staff user, **When** they submit a simulator message with a valid client name and non-empty message body, **Then** the system creates an inbound message linked to a conversation for that client within the user's tenant.
2. **Given** an authenticated Staff user, **When** they submit a simulator message for a client who already has an open conversation, **Then** the message is added to the existing conversation rather than creating a duplicate.
3. **Given** an authenticated Staff user, **When** they submit a message with an empty body, **Then** the system rejects the submission with a clear validation error.
4. **Given** a message is submitted, **When** it is saved, **Then** it appears in the tenant's inbox with a status indicating it is new and awaiting a response.

---

### User Story 2 — Use Preset Demo Messages (Priority: P1)

A staff planner preparing for a product demo opens the simulator and selects from a list of preset example messages — covering price enquiries, guest-count changes, cancellations, complaints, and payment issues. Selecting a preset populates the message field instantly. The planner can edit it before sending or send it as-is.

**Why this priority**: Demo operators need to inject realistic messages quickly without typing. Preset messages cover the five key emotional/functional scenarios that stress-test the AI reply and escalation pipeline. They eliminate setup friction during live demonstrations.

**Independent Test**: Open the simulator; confirm at least five preset messages are available covering different scenario types. Select one preset; confirm the message body is populated in the form. Submit without editing; verify the message is created correctly.

**Acceptance Scenarios**:

1. **Given** the simulator is open, **When** the user views the preset list, **Then** at least five preset messages are available covering price enquiry, guest-count change, cancellation, payment issue, and complaint scenarios.
2. **Given** a preset is selected, **When** the user views the form, **Then** the message body field is populated with the preset text and the user can edit it freely before submitting.
3. **Given** a preset message is submitted without edits, **When** it is saved, **Then** the full preset text is stored as the message body — no truncation or alteration.
4. **Given** a user selects a preset and edits the text, **When** they submit, **Then** the edited version (not the original preset) is stored.

---

### User Story 3 — Attach a Simulated Message to an Existing Conversation (Priority: P2)

A staff planner wants to add a follow-up message from the same client to a conversation that is already open. They open the simulator, select the existing conversation by client name or conversation ID, and submit a new message. The message is appended to that conversation's thread.

**Why this priority**: Real client exchanges involve multiple messages. Without the ability to add follow-up messages to an existing conversation, the demo inbox will only ever show single-message threads — making it impossible to demonstrate conversation history, context-aware AI replies, or escalation flows.

**Independent Test**: Create a first message (US1). Open the simulator again, select the same client/conversation, submit a second message. Verify the second message appears in the same conversation thread, not as a new conversation.

**Acceptance Scenarios**:

1. **Given** an open conversation exists for a client, **When** the user selects that conversation in the simulator and submits a new message, **Then** the new message is appended to the existing conversation thread.
2. **Given** the simulator is open, **When** the user browses existing conversations, **Then** only conversations belonging to the authenticated tenant are displayed — no other tenant's conversations are shown.
3. **Given** the user selects an existing conversation and submits a message, **When** the message is saved, **Then** the conversation's `updated_at` timestamp is refreshed.

---

### User Story 4 — View Simulator Audit Trail (Priority: P3)

A manager will later be able to verify which simulated messages were injected in their workspace and when through the dedicated audit-log feature. For this simulator feature, each successful write emits/records a `simulator_message_created` event if audit infrastructure exists.

**Why this priority**: Auditability matters for later review, but full audit log UI/API is a separate feature. This simulator only needs to provide the event hook/data.

**Independent Test**: Inject two simulator messages and verify the simulator emits/records `simulator_message_created` event data with actor, conversation ID, message ID, client name when available, and timestamp if audit infrastructure exists.

**Acceptance Scenarios**:

1. **Given** a simulator message is created, **When** audit infrastructure exists, **Then** one `simulator_message_created` event is recorded/emitted.
2. **Given** a closed conversation is re-opened by a simulator message, **When** the event is recorded/emitted, **Then** the same event includes `detail.reopened=true`; a second audit record is not required.
3. **Given** full audit log browsing is needed, **When** that feature is implemented, **Then** it uses these event details and tenant-scopes results.

---

### Edge Cases

- What happens when a message body contains only whitespace? The backend must treat it as empty and reject it — the same validation as a fully empty field.
- What happens when the same client name is used with a different contact detail? A new conversation is created — the system matches conversations by exact client name + contact combination, not by name alone.
- What happens when a simulator message is injected into a conversation whose status is `closed`? The message is added and the conversation status is automatically re-opened to `open`, since a new inbound message implies the client has re-engaged.
- What happens when the simulator is used with very long message bodies? Messages are capped at 4,000 characters — matching the practical limit of a real WhatsApp message — and the form shows a character counter.
- What happens when a staff user submits a message for a client name that contains special characters or emoji? The message body and client name are stored as-is. No sanitisation beyond standard input validation.

---

## MVP Scope

- Simulator form: client name (required), client contact (optional, e.g., phone or email), message body (required, 1–4,000 characters)
- Five preset messages covering: price enquiry, guest-count change, cancellation, payment issue, and complaint
- Create new conversation if no matching client name + contact exists in the tenant
- Append message to existing open conversation if matching client is found
- Re-open closed conversation when a simulator message is injected into it
- `direction=inbound` set on all simulator-created messages
- Message status set to `unread` (or equivalent new-and-awaiting-response state) on creation
- one `simulator_message_created` audit event emitted/recorded for every successful submission if audit infrastructure exists
- Tenant isolation: messages scoped to authenticated user's tenant; no cross-tenant visibility
- Empty or whitespace-only message bodies rejected with a validation error
- Character limit: 4,000 characters per message

---

## Out of Scope

- Real WhatsApp Business API integration (future feature)
- Receiving messages from actual phone numbers
- Outbound (agent reply) message creation via the simulator — the simulator only injects inbound messages
- Media attachments (images, voice notes, documents via simulator)
- Message scheduling or delayed delivery
- Bulk message injection (importing a list of messages at once)
- Simulated client phone numbers that look up real contacts
- Webhook simulation or event streaming
- Read-receipt simulation

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Client name | Simulator form | Required. Used to find or create a conversation. |
| Client contact | Simulator form | Optional. Phone number or email. Combined with client name to identify a unique client. |
| Message body | Simulator form or preset | Required. 1–4,000 characters. Whitespace-only is rejected. |
| Preset selection | Simulator UI | Optional. Populates the message body field; can be edited before submission. |
| Existing conversation selection | Simulator UI | Optional. Explicitly targets an open conversation rather than relying on client-name matching. |
| Authenticated session | JWT | Provides `tenant_id` and `user_id`; never supplied by the client. |

---

## Outputs

| Output | Description |
|--------|-------------|
| Inbound message record | Created in the tenant's conversation with `direction=inbound`, status=`unread`, linked to the correct conversation. |
| New or updated conversation | Created if no matching client conversation exists; updated (`updated_at` refreshed) if one does; re-opened if the existing conversation was `closed`. |
| `simulator_message_created` event | Emitted/recorded with actor, client name when available, conversation ID, message ID, and `reopened=true` when applicable if audit infrastructure exists. |
| Validation error | Returned for empty/whitespace message body or message exceeding 4,000 characters. |
| Simulator confirmation | UI feedback confirming the message was injected and naming the conversation it was added to. |

---

## Main Workflow

1. **Staff opens the simulator** — The simulator panel or page is accessible from within the tenant dashboard (Staff and Manager roles only).
2. **Client is identified** — Staff enters a client name and optional contact detail, or selects an existing conversation from a dropdown list.
3. **Message is composed** — Staff types a message body, or selects a preset from the list (which populates the field for optional editing).
4. **Submission validated** — The backend validates: message body is non-empty and non-whitespace; body does not exceed 4,000 characters; client name is non-empty.
5. **Conversation resolved** — The backend looks up an existing open conversation matching the client name + contact within the authenticated tenant. If none exists, a new conversation is created. If a matching conversation is `closed`, it is re-opened.
6. **Message created** — An inbound message record is created with `direction=inbound`, `status=unread`, linked to the resolved conversation, with `tenant_id` from the JWT.
7. **Audit event emitted** — A single `simulator_message_created` event is recorded/emitted if audit infrastructure exists.
8. **Confirmation returned** — The system returns success with the message ID and conversation ID. The simulator form is cleared (or retains the client name for follow-up injection).

---

## Alternative Workflows

### Empty Message Submission

1. Staff submits the simulator form with an empty or whitespace-only message body.
2. The backend rejects the request with a 422 validation error.
3. The error message is shown inline in the form: "Message cannot be empty."
4. No message is created; no audit event is written.

### Message Exceeds Character Limit

1. Staff types or pastes a message body longer than 4,000 characters.
2. The form shows a live character counter turning red when the limit is reached.
3. If submitted anyway, the backend rejects with a 422 validation error.
4. No message is created.

### Injecting into a Closed Conversation

1. Staff selects an existing conversation that is in `closed` status.
2. The backend accepts the message, appends it to the conversation, and automatically changes the conversation status from `closed` to `open`.
3. The single simulator audit event includes `detail.reopened=true`.
4. The inbox now shows the conversation as open with the new unread message.

### Preset Selected but Not Edited

1. Staff selects a preset (e.g., "I want to cancel. Is the deposit refundable?") and submits immediately.
2. The preset text is stored verbatim as the message body.
3. No distinction is made in the stored message between a preset and a manually typed message — the body is just text.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | A submitted simulator message creates an inbound message record linked to the correct tenant's conversation | Integration test: check `direction=inbound`, correct `tenant_id`, correct `conversation_id` |
| AC-02 | Submitting for a new client creates a new conversation | Integration test: query conversations before and after; count increases by 1 |
| AC-03 | Submitting for an existing client appends to the existing conversation | Integration test: count messages in conversation before and after; conversation count unchanged |
| AC-04 | Injecting into a closed conversation re-opens it | Integration test: set conversation `status=closed`, inject message, assert `status=open` |
| AC-05 | Empty message body returns a validation error and creates no record | Integration test: submit empty body, assert 422 and zero new messages in DB |
| AC-06 | Whitespace-only message body is rejected identically to empty | Integration test: submit `"   "`, assert 422 |
| AC-07 | Message body exceeding 4,000 characters is rejected | Integration test: submit 4,001-char body, assert 422 |
| AC-08 | Created message has `direction=inbound` and `status=unread` | DB assertion on created record |
| AC-09 | `simulator_message_created` event is emitted/recorded for every successful submission when audit infrastructure exists | Test event call/record with correct action, actor, conversation_id |
| AC-10 | Simulated messages from Tenant A are invisible to authenticated users of Tenant B | Integration test: inject for Tenant A, query inbox as Tenant B, assert zero results |
| AC-11 | Five preset messages are available covering all five required scenario types | UI test: open simulator, assert five presets present and each covers its named scenario |
| AC-12 | `tenant_id` is derived from the authenticated session — not from any client-supplied value | Integration test: submit with mismatched `tenant_id` in body; verify session value is used |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Provides tenant/user foundation, tenant isolation rules, `TenantContext`, and tenant-scoped service pattern. |
| Spec 002 — Authentication and Roles | Required | Provides authenticated session with `tenant_id`, `user_id`, and `role`. The simulator is accessible to `staff` and `manager` roles only. Platform Admin has no access to the simulator. |

---

## AI Behavior

The simulator itself does not invoke AI. However, it is the primary seed mechanism that provides the inbound messages that AI features (reply suggestions, escalation detection) will later process.

The following design constraints ensure AI downstream compatibility:

- Simulator-created messages are structurally identical to real inbound messages — the AI pipeline cannot and need not distinguish between them.
- The `direction=inbound` flag on simulator messages is what makes them eligible for AI reply suggestion generation (when that feature exists).
- The AI reply suggestion feature (future) will be triggered by new inbound messages regardless of whether they came from the simulator or a real channel — this is intentional.
- The `simulator_message_created` audit event type allows managers and the platform team to filter simulator-generated data out of AI accuracy metrics if needed.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is derived exclusively from the authenticated JWT. Any `tenant_id` or `conversation_id` supplied in the request body is validated against the session — if they belong to a different tenant, the request is rejected with 403 and an audit event is written. |
| **SR-02: Role restriction** | Only `staff` and `manager` roles may use the simulator. Platform Admin has no access. Requests with insufficient role return 403. |
| **SR-03: No cross-tenant conversation selection** | When a user selects an existing conversation to inject into, the backend verifies the conversation's `tenant_id` matches the authenticated user's `tenant_id`. A mismatch returns 403. |
| **SR-04: Input validation at the backend** | Message body and client name validation (empty check, whitespace check, length check) is enforced server-side. Frontend validation is a UX convenience only — the backend does not trust it. |
| **SR-05: Audit event on every successful write** | Every successful simulator message creation emits/records one simulator event if audit infrastructure exists. Failed validation does not create audit events. Permission failures follow Spec 001 actor-tenant audit policy once audit logging exists. |
| **SR-06: No real client data exposure** | The simulator only reads the list of existing conversations within the authenticated tenant. It never exposes client contact details, message history, or any data belonging to another tenant. |

---

## Assumptions

- The simulator is accessible from within the tenant dashboard as a panel or dedicated page — not as a public or unauthenticated endpoint.
- Client-name matching for conversation lookup uses exact string matching (case-insensitive) plus optional contact field. Fuzzy matching is out of scope for MVP.
- The five preset messages are hard-coded in the frontend for MVP; a configurable preset library is a post-MVP enhancement.
- The simulator does not simulate WhatsApp-specific metadata such as message IDs from WhatsApp, delivery timestamps, or phone numbers. The message body is all that is captured.
- A "conversation" in this context is the `conversations` table entity introduced by this simulator feature so later inbox and AI features can reuse the same structure.
- The `status=unread` field is introduced by this feature's `messages` schema work and is reused by the inbox.
- Platform Admin does not need simulator access for any provisioning or demo workflow — they use the tenant admin endpoints instead.
