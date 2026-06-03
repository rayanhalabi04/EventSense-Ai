# Data Model: Message Inbox

**Branch**: `004-message-inbox` | **Phase**: 1 — Design

---

## Schema Changes

**None.** This feature is read-only. It uses existing tables from Spec 001 (`conversations`, `messages`) and the `status` column added to `messages` in Spec 003. No Alembic migration is required.

---

## Existing Entities Used

### `conversations` (Spec 001)

Columns relevant to the inbox:

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | Row identifier; navigation target `/conversations/{id}` |
| `tenant_id` | UUID | Mandatory filter on every query |
| `client_name` | VARCHAR(255) | Display + search |
| `client_contact` | VARCHAR(320) | Display + search |
| `status` | ENUM | Display badge + status filter |
| `updated_at` | TIMESTAMPTZ | Primary sort key (DESC) |
| `created_at` | TIMESTAMPTZ | Fallback display when no messages exist |

### `messages` (Spec 001 + Spec 003)

Columns relevant to the inbox:

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | Subquery target (latest message lookup) |
| `tenant_id` | UUID | Included in EXISTS search subquery filter |
| `conversation_id` | UUID | Join key |
| `body` | TEXT | Preview (truncated to 100 chars) + search |
| `sent_at` | TIMESTAMPTZ | Ordering within conversation; displayed as latest message time |
| `direction` | ENUM | Shown on inbox item (inbound = client, outbound = agent) |
| `status` | ENUM (`unread`/`read`) | Unread filter; unread count aggregate; `has_unread` flag |

---

## Pydantic Schemas (`backend/app/schemas/inbox.py`)

### Query Parameters

```python
class InboxFilters(BaseModel):
    unread_only: bool = False
    status: ConversationStatus | None = None   # open / closed / escalated / None (all)
    search: str | None = None                  # min 2 chars when present
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @validator("search")
    def search_min_length(cls, v):
        if v is not None and len(v.strip()) < 2:
            raise ValueError("Search term must be at least 2 characters")
        return v.strip() if v else None
```

### Response: Single Inbox Item

```python
class InboxItemResponse(BaseModel):
    conversation_id: UUID
    client_name: str
    client_contact: str | None
    latest_message_preview: str | None   # body[:100] + "…" if truncated; None if no messages
    latest_message_at: datetime | None   # sent_at of latest message; None if no messages
    latest_message_direction: str | None # "inbound" | "outbound" | None
    unread_count: int                    # count of messages with status=unread in this conversation
    has_unread: bool                     # unread_count > 0
    conversation_status: str             # "open" | "closed" | "escalated"
    updated_at: datetime
```

### Response: Paginated Inbox List

```python
class InboxResponse(BaseModel):
    items: list[InboxItemResponse]
    total: int           # total conversations matching current filters (for pagination)
    total_unread: int    # tenant-wide unread conversation count (ignores active filters; drives nav badge)
    page: int
    page_size: int
    total_pages: int
```

---

## Inbox Query Logic (SQLAlchemy)

```python
# backend/app/services/inbox_service.py

async def get_inbox(
    session: AsyncSession,
    tenant_id: UUID,
    filters: InboxFilters,
) -> InboxResponse:

    # 1. Correlated subquery: latest message per conversation
    latest_msg_sq = (
        select(Message.id)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.sent_at.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )

    # 2. Correlated subquery: unread count per conversation
    unread_sq = (
        select(func.count())
        .where(
            Message.conversation_id == Conversation.id,
            Message.tenant_id == tenant_id,
            Message.status == MessageStatus.unread,
        )
        .correlate(Conversation)
        .scalar_subquery()
    )

    # 3. Base query
    stmt = (
        select(
            Conversation,
            Message.body.label("latest_body"),
            Message.sent_at.label("latest_sent_at"),
            Message.direction.label("latest_direction"),
            unread_sq.label("unread_count"),
        )
        .outerjoin(Message, Message.id == latest_msg_sq)
        .where(Conversation.tenant_id == tenant_id)
    )

    # 4. Apply filters
    if filters.status:
        stmt = stmt.where(Conversation.status == filters.status)
    if filters.unread_only:
        stmt = stmt.where(unread_sq > 0)
    if filters.search:
        pattern = f"%{filters.search}%"
        search_exists = exists(
            select(Message.id)
            .where(
                Message.conversation_id == Conversation.id,
                Message.body.ilike(pattern),
                Message.tenant_id == tenant_id,
            )
        )
        stmt = stmt.where(
            or_(
                Conversation.client_name.ilike(pattern),
                Conversation.client_contact.ilike(pattern),
                search_exists,
            )
        )

    # 5. Count total (for pagination)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # 6. Apply sort and pagination
    stmt = stmt.order_by(Conversation.updated_at.desc())
    stmt = stmt.limit(filters.page_size).offset((filters.page - 1) * filters.page_size)

    rows = (await session.execute(stmt)).all()

    # 7. Compute total_unread (tenant-wide, ignores active filters)
    total_unread_stmt = (
        select(func.count(func.distinct(Message.conversation_id)))
        .where(
            Message.tenant_id == tenant_id,
            Message.status == MessageStatus.unread,
        )
    )
    total_unread = (await session.execute(total_unread_stmt)).scalar_one()

    # 8. Build response
    items = [
        InboxItemResponse(
            conversation_id=row.Conversation.id,
            client_name=row.Conversation.client_name,
            client_contact=row.Conversation.client_contact,
            latest_message_preview=truncate_preview(row.latest_body),
            latest_message_at=row.latest_sent_at,
            latest_message_direction=row.latest_direction,
            unread_count=row.unread_count or 0,
            has_unread=(row.unread_count or 0) > 0,
            conversation_status=row.Conversation.status.value,
            updated_at=row.Conversation.updated_at,
        )
        for row in rows
    ]

    return InboxResponse(
        items=items,
        total=total,
        total_unread=total_unread,
        page=filters.page,
        page_size=filters.page_size,
        total_pages=math.ceil(total / filters.page_size) if total else 0,
    )
```

---

## Frontend State Shape (`useInbox` hook)

```typescript
interface InboxFilters {
  unreadOnly: boolean;
  status: "open" | "closed" | "escalated" | null;
  search: string;
  page: number;
}

interface UseInboxResult {
  items: InboxItemResponse[];
  total: number;
  totalUnread: number;
  totalPages: number;
  isLoading: boolean;
  error: string | null;
  filters: InboxFilters;
  setFilter: (key: keyof InboxFilters, value: unknown) => void;
  clearFilters: () => void;
  setSearch: (term: string) => void;
  setPage: (page: number) => void;
}
```

All filter state is synchronised with URL search params via `react-router`'s `useSearchParams`.

---

## Frontend Component Tree

```
InboxPage                     /inbox
├── InboxFilters              filter controls (read status toggle + status select)
├── InboxSearch               debounced search input (300ms, min 2 chars)
├── InboxList
│   ├── InboxItem × N         one card per conversation
│   └── InboxEmptyState       two variants: global-empty / filtered-empty
└── InboxPagination           previous/next + "Page X of Y"
```

Navigation: `InboxItem` click → `navigate('/conversations/' + conversation_id)` (Spec 005 placeholder).

Unread badge: `totalUnread` from `useInbox` is passed to the sidebar nav `NavItem` for the inbox link.
