# Tasks: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Depends on**: Spec 001 (tenant foundation, tenant-scoped service pattern, ForbiddenError contract) and Spec 002 (JWT auth, TenantContext, require_role, staff/manager roles). This feature creates the basic conversations/messages schema it needs.

**Total tasks**: 30 across 7 phases

**Format**: `[ID] [P?] [Story?] Description — file path`
- `[P]` = parallelizable (different files, no incomplete dependency)
- `[US#]` = maps to user story in spec.md
- Setup and Foundational phases carry no story label

---

## Phase 1: Setup

**Purpose**: Add the one schema change this feature requires, register the new audit action constant, create empty schema and data files. No logic.

- [ ] T001 Write Alembic migration `0010_create_conversations_messages`: create `conversation_status`, `message_direction`, `message_status`, `conversations`, and `messages` with non-null `tenant_id` columns and indexes in `backend/alembic/versions/0010_create_conversations_messages.py`
- [ ] T002 [P] Add `MessageStatus` string enum (`unread`, `read`) to `backend/app/models/message.py` and add `status: Mapped[MessageStatus]` column with `default=MessageStatus.unread` to the `Message` model
- [ ] T003 [P] Add/define `simulator_message_created` audit event constant for future audit integration; if audit service is not implemented yet, keep it as a simulator event constant
- [ ] T004 [P] Create `backend/app/schemas/simulator.py` as an empty file (will be filled in Phase 2) and add it to `backend/app/schemas/__init__.py` imports
- [ ] T005 [P] Create `frontend/src/data/simulatorPresets.ts` with the `SimulatorPreset` interface and `SIMULATOR_PRESETS` array containing the five hard-coded presets: price enquiry (`"Can you send me your wedding package prices?"`), guest count change (`"We need to change the guest count from 150 to 220."`), cancellation (`"I want to cancel. Is the deposit refundable?"`), payment issue (`"I paid the deposit but no one confirmed."`), complaint (`"I am unhappy with the decoration sample."`)

**Checkpoint**: `alembic upgrade head` applies migration 0010 cleanly; `\d messages` shows `status message_status NOT NULL DEFAULT 'unread'`; `SIMULATOR_PRESETS.length === 5` in a quick Vitest import test.

---

## Phase 2: Foundational — Simulator Service and Schemas

**Purpose**: The Pydantic schemas and `SimulatorService` business logic that all endpoints and tests depend on. No HTTP layer yet.

**⚠️ CRITICAL**: Complete before Phases 3–6.

- [ ] T006 Define `SimulatorMessageRequest(BaseModel)` in `backend/app/schemas/simulator.py`: fields `client_name: str | None = None`, `client_contact: str | None = None`, `body: str`, `conversation_id: UUID | None = None`; use Pydantic v2 `@field_validator("body")` for non-empty/≤4000 checks and `@model_validator(mode="after")` to require either `conversation_id` or non-empty `client_name`
- [ ] T007 [P] Define `SimulatorMessageResponse(BaseModel)` in `backend/app/schemas/simulator.py`: fields `message_id: UUID`, `conversation_id: UUID`, `is_new_conversation: bool`, `conversation_status: str`, `tenant_id: UUID`
- [ ] T008 Define `SimulatorConversationItem(BaseModel)` and `SimulatorConversationsResponse(BaseModel)` in `backend/app/schemas/simulator.py`: `SimulatorConversationItem` has `id: UUID`, `client_name: str`, `client_contact: str | None`, `status: str`, `message_count: int`, `updated_at: datetime`; `SimulatorConversationsResponse` has `items: list[SimulatorConversationItem]`, `total: int`
- [ ] T009 Implement `SimulatorService.resolve_or_create_conversation(session, tenant_id, client_name, client_contact, conversation_id, event_recorder, ctx) -> tuple[Conversation, bool, bool]` in `backend/app/services/simulator_service.py`: (1) if `conversation_id` supplied → fetch, verify `conv.tenant_id == tenant_id` (raise `ForbiddenError` on mismatch; future audit logs actor tenant only), re-open if `status=="closed"`, return `(conv, False, was_closed)`; (2) if no `conversation_id` → require non-empty client name, query `WHERE tenant_id=:tid AND LOWER(client_name)=LOWER(:name) AND client_contact IS NOT DISTINCT FROM :contact ORDER BY created_at DESC LIMIT 1`; re-open if found and closed; create new if not found; return `(conv, is_new, was_closed)`
- [ ] T010 Implement `SimulatorService.create_inbound_message(session, tenant_id, conversation_id, body, actor_user_id) -> Message` in `backend/app/services/simulator_service.py`: insert `Message(tenant_id=tenant_id, conversation_id=conversation_id, direction=MessageDirection.inbound, status=MessageStatus.unread, body=body, sender_user_id=None, sent_at=utcnow())`; update `conversation.updated_at = utcnow()` within the same transaction
- [ ] T011 [P] Implement `SimulatorService.list_tenant_conversations(session, tenant_id) -> list[ConversationSummary]` in `backend/app/services/simulator_service.py`: query `conversations WHERE tenant_id=:tid ORDER BY updated_at DESC`; include a subquery or joined aggregate for `message_count`; return list suitable for `SimulatorConversationItem`

**Checkpoint**: Instantiate `SimulatorService` in a Python shell; call `resolve_or_create_conversation` against a test DB; confirm it creates a conversation on first call and reuses it on second call with the same client name (case-insensitive).

---

## Phase 3: User Story 1 — Inject a New Inbound Message (Priority: P1)

**Goal**: Staff submits a simulator form with client name and message body → a new inbound message appears in the tenant's conversation, linked to the correct tenant, with `direction=inbound` and `status=unread`.

**Independent Test**: POST `/api/v1/simulator/messages` as Staff with a new client name → assert 201, `is_new_conversation=true`, query DB and confirm message has `direction=inbound`, `status=unread`, `tenant_id` matches JWT.

- [ ] T012 [US1] Create `backend/app/api/v1/simulator.py` with an `APIRouter(prefix="/simulator", tags=["simulator"])`; implement `POST /messages` handler: extract `ctx = Depends(require_role(UserRole.staff, UserRole.manager))`; call `SimulatorService.resolve_or_create_conversation(...)` then `SimulatorService.create_inbound_message(...)`; emit/record one `simulator_message_created` event if audit infrastructure exists with `detail={"conversation_id": str(conv.id), "client_name": req.client_name or conv.client_name, "is_new_conversation": is_new, "reopened": was_closed}`; return `SimulatorMessageResponse`
- [ ] T013 [US1] Mount the simulator router at `/api/v1/simulator` in `backend/app/main.py`
- [ ] T014 [P] [US1] Create `frontend/src/api/simulator.ts`: implement `injectMessage(payload: SimulatorMessagePayload): Promise<SimulatorMessageResult>` calling `POST /api/v1/simulator/messages` using the Axios client from Spec 002; define `SimulatorMessagePayload` and `SimulatorMessageResult` TypeScript interfaces matching the API contract
- [ ] T015 [P] [US1] Implement `CharacterCounter` component in `frontend/src/components/simulator/CharacterCounter.tsx`: accepts `current: number` and `max: number = 4000` props; renders `"{current} / {max}"` in grey when under limit and red when at or over limit
- [ ] T016 [US1] Implement `SimulatorForm` component in `frontend/src/components/simulator/SimulatorForm.tsx`: fields for `client_name` (required only when no conversation is selected), `client_contact` (optional), `body` (textarea with `CharacterCounter`); submit button disabled when `body.trim().length === 0`, `body.length > 4000`, or neither `conversation_id` nor non-empty `client_name` exists; on submit call `injectMessage()`; on success display confirmation; clear `body` field on success
- [ ] T017 [US1] Implement `SimulatorPage` in `frontend/src/pages/SimulatorPage.tsx`: page heading "Message Simulator"; renders `SimulatorForm`; `<ProtectedRoute><RoleGuard allowedRoles={["staff", "manager"]}>`
- [ ] T018 [US1] Add `/simulator` route to `frontend/src/App.tsx` wrapped in `<ProtectedRoute>` and `<RoleGuard allowedRoles={["staff", "manager"]}>`
- [ ] T019 [US1] Write integration tests in `backend/tests/integration/test_simulator.py`: `test_simulator_creates_inbound_message_with_correct_fields` (AC-01, AC-08), `test_simulator_creates_new_conversation_for_unknown_client` (AC-02), `test_simulator_rejects_empty_body` (AC-05), `test_simulator_rejects_whitespace_only_body` (AC-06), `test_simulator_rejects_body_exceeding_4000_chars` (AC-07), `test_simulator_emits_event_on_success_if_available` (AC-09), `test_simulator_message_invisible_to_other_tenant` (AC-10), `test_simulator_platform_admin_returns_403` (SR-02), `test_simulator_tenant_id_from_jwt_not_body` (AC-12), `test_simulator_requires_conversation_id_or_client_name`

**Checkpoint**: `pytest tests/integration/test_simulator.py::test_simulator_creates_inbound_message_with_correct_fields tests/integration/test_simulator.py::test_simulator_creates_new_conversation_for_unknown_client -v` pass; curl POST to `/api/v1/simulator/messages` as Staff returns 201 with `is_new_conversation=true`.

---

## Phase 4: User Story 2 — Preset Demo Messages (Priority: P1)

**Goal**: Staff opens the simulator and clicks a preset chip to instantly populate the message body. Presets cover all five required scenario types and can be edited before submission.

**Independent Test**: Import `SIMULATOR_PRESETS` — assert 5 entries, one per required scenario type. In the UI, click each preset chip and confirm the body textarea contains exactly that preset's text.

- [ ] T020 [P] [US2] Implement `PresetPicker` component in `frontend/src/components/simulator/PresetPicker.tsx`: renders a horizontal row of clickable `shadcn/ui Button` chips, one per entry in `SIMULATOR_PRESETS`; each chip shows `preset.label`; `onClick` prop calls `onSelect(preset.body)` to notify the parent form
- [ ] T021 [US2] Wire `PresetPicker` into `SimulatorForm`: add `PresetPicker` above the `body` textarea; when a preset is selected, set the `body` field state to `preset.body` (replacing any existing content, allowing subsequent edits)
- [ ] T022 [US2] Add frontend unit test in `frontend/src/data/simulatorPresets.test.ts` asserting `SIMULATOR_PRESETS.length === 5` and each of the five scenario labels is present (price, count, cancel, payment, complaint)

**Checkpoint**: All 5 preset chips render in the UI; clicking each populates the textarea; the populated text is editable; submitting a preset message creates a valid inbound message in the DB.

---

## Phase 5: User Story 3 — Attach to Existing Conversation (Priority: P2)

**Goal**: Staff selects an existing conversation from the dropdown instead of typing a new client name. The message is appended to that conversation thread. Closed conversations are automatically re-opened.

**Independent Test**: Create a conversation via US1. Open the simulator, select that conversation from the dropdown, submit a second message. Assert DB has 2 messages under the same `conversation_id` and total conversation count is unchanged.

- [ ] T023 [US3] Implement `GET /simulator/conversations` handler in `backend/app/api/v1/simulator.py`: `ctx = Depends(require_role(UserRole.staff, UserRole.manager))`; call `SimulatorService.list_tenant_conversations(session, ctx.tenant_id)`; return `SimulatorConversationsResponse`
- [ ] T024 [P] [US3] Add `listConversations(): Promise<SimulatorConversationsResponse>` function to `frontend/src/api/simulator.ts` calling `GET /api/v1/simulator/conversations`
- [ ] T025 [P] [US3] Implement `ConversationSelector` component in `frontend/src/components/simulator/ConversationSelector.tsx`: a `shadcn/ui Select` dropdown backed by `listConversations()`; each option displays `"{client_name} ({status})"` with `updated_at` shown as a subtitle; triggers `onSelect(conversationId)` when a conversation is chosen; shows a "— New conversation —" option at the top to deselect and return to manual client entry
- [ ] T026 [US3] Wire `ConversationSelector` into `SimulatorForm`: render `ConversationSelector` above the client name/contact fields; when a conversation is selected, hide the client name and contact inputs (they are redundant) and set the form's `conversation_id` field; when "New conversation" is selected, show the client fields again and clear `conversation_id`
- [ ] T027 [US3] Add follow-up and isolation tests to `backend/tests/integration/test_simulator.py`: `test_simulator_appends_to_existing_conversation` (AC-03), `test_simulator_reopens_closed_conversation` (AC-04), `test_simulator_conversation_list_scoped_to_tenant` (AC-10 for GET), `test_simulator_cross_tenant_conversation_id_returns_403` (SR-03, AC-12)

**Checkpoint**: `pytest tests/integration/test_simulator.py -v` passes all 13 tests; dropdown in UI populates from `GET /api/v1/simulator/conversations`; selecting a conversation and submitting appends the message to the existing thread.

---

## Phase 6: User Story 4 — Simulator Audit Event Hook (Priority: P3)

**Goal**: Simulator writes expose one `simulator_message_created` event payload for the later audit-log feature. Full audit log browsing is deferred.

**Independent Test**: Inject a message and assert the event hook is called or recorded with actor, tenant, message ID, conversation ID, client name when available, and `reopened` flag.

- [ ] T028 [US4] Add or verify a small event-recorder seam for simulator writes so the later audit feature can persist `simulator_message_created` without changing simulator business logic
- [ ] T029 [US4] Add event hook tests to `backend/tests/integration/test_simulator.py`: `test_simulator_event_contains_actor_conversation_and_message`, `test_simulator_reopen_uses_single_event_with_reopened_true`

**Checkpoint**: `pytest tests/integration/test_simulator.py -v` passes; simulator emits/records one event per successful message and does not require an audit-log API.

---

## Phase 7: Polish — Quickstart Validation

**Purpose**: End-to-end validation of the feature and documentation accuracy.

- [ ] T030 Run `alembic upgrade head`, run the curl commands in `specs/003-message-simulator/quickstart.md` end-to-end (inject message, follow-up, empty-body rejection, cross-tenant isolation); update quickstart if any command output differs from documented expected output in `specs/003-message-simulator/quickstart.md`
**Checkpoint**: `pytest tests/integration/test_simulator.py -v` passes; quickstart curl commands produce the documented output.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup: migration, MessageStatus, AuditAction constant, presets constant)
  └── Phase 2 (Foundational: Pydantic schemas + SimulatorService)
        ├── Phase 3 (US1: POST endpoint, SimulatorForm, core tests)  ← P1, start here
        │     └── Phase 4 (US2: PresetPicker wired into form)        ← P1, low effort
        │           └── Phase 5 (US3: GET conversations, ConversationSelector)
        │                 └── Phase 6 (US4: Audit trail verification)
        │                           └── Phase 7 (Polish)
```

### User Story Dependencies

| Story | Depends on | Notes |
|-------|-----------|-------|
| US1 (Inject message) | Phase 1 + 2 | Core flow; everything else builds on this |
| US2 (Presets) | US1 `SimulatorForm` renders | Presets wire into existing form; parallel to US1 frontend |
| US3 (Existing conversation) | US1 + GET endpoint (T023) | `conversation_id` path through `SimulatorService` already exists |
| US4 (Audit trail) | US1 (audit events written) | Just verifies existing audit log endpoint with filter |

### Within Each Phase

- All `[P]`-tagged tasks write to different files — safe to run concurrently
- T009 (resolve logic) and T010 (create message) within Phase 2 must both complete before any endpoint test
- T012 (endpoint) must complete before T019 (integration tests)
- T023 (GET endpoint) must complete before T024–T026 (frontend conversation selector)

---

## Parallel Execution Examples

### Phase 2 — Schemas and service methods

```
Parallel:
  T007  SimulatorMessageResponse schema
  T008  SimulatorConversationItem + SimulatorConversationsResponse schemas
  T011  list_tenant_conversations method

Sequential (depends on T006 validators):
  T006  SimulatorMessageRequest with validators
  T009  resolve_or_create_conversation (needs Conversation + Message models)
  T010  create_inbound_message (needs MessageStatus from T002)
```

### Phase 3 (US1) — Backend and frontend in parallel

```
Backend (sequential — each step depends on prior):
  T012  POST /simulator/messages endpoint
  T013  Mount router in main.py

Frontend (parallel once T012 is reachable):
  T014  simulator.ts API module
  T015  CharacterCounter component
  T016  SimulatorForm (needs T014 + T015)
  T017  SimulatorPage (needs T016)
  T018  App.tsx route (needs T017)
```

### Phase 5 (US3) — Backend and frontend in parallel

```
Parallel:
  T023  GET /simulator/conversations (backend)
  T024  listConversations() (frontend API)
  T025  ConversationSelector component

Then sequential:
  T026  Wire ConversationSelector into SimulatorForm
  T027  Follow-up and isolation tests
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1 (Setup) → ~5 tasks
2. Complete Phase 2 (Foundational) → ~6 tasks
3. Complete Phase 3 (US1: Inject message) → ~8 tasks
4. **STOP and VALIDATE**: POST `/api/v1/simulator/messages` works; 9 core tests pass
5. Complete Phase 4 (US2: Presets) → ~3 tasks
6. **STOP and VALIDATE**: All 5 presets populate the form; demo flow end-to-end works

### Incremental Delivery

| Milestone | Phases | Verifiable outcome |
|-----------|--------|--------------------|
| Schema + service | 1–2 | Migration applies; SimulatorService unit-testable |
| Core injection | + 3 | POST endpoint works; 9 tests pass; curl demo works |
| Presets | + 4 | 5 preset chips; populated body submits correctly |
| Conversation selector | + 5 | Dropdown lists existing conversations; follow-up messages work; 13 tests pass |
| Audit trail | + 6 | Manager can filter audit log to simulator events; 16 tests pass |
| Validated | + 7 | Quickstart end-to-end confirmed |

---

## Notes

- Spec 001 tenant foundation and Spec 002 auth foundations are assumed to exist. This feature creates conversations/messages and emits simulator events for future audit integration.
- No real WhatsApp API, calendar syncing, AI classifier, RAG, suggested replies, full inbox page, or message detail page tasks are included
- The conversations/messages schema and `status` column are the only schema changes in this feature
- Preset messages are frontend-only constants — no database table or backend endpoint for presets
- `tenant_id` on every created record comes exclusively from `ctx.tenant_id` (JWT-derived) — the service layer never reads `tenant_id` from the request body
- All 16 integration tests map 1:1 to the 12 acceptance criteria + 4 additional security/role checks
