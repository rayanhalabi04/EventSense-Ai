# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is an **EventSense AI frontend** that is either being initialized or actively built. The repo currently contains documentation only — no `package.json` or source code exists yet. Before writing any code, check whether a framework has been scaffolded since this file was written.

## Planned Stack

- **Framework**: React + TypeScript + Vite
- **Styling**: Tailwind CSS (configured with EventSense design tokens)
- **Icons**: Lucide (outline style, 1.75–2px stroke — no other icon sets)
- **Fonts**: Newsreader (display/headline) + Inter (UI/body) — loaded from Google Fonts
- **Server state**: TanStack Query (React Query)
- **Client state**: Zustand
- **HTTP**: Axios with Bearer token interceptor
- **Testing**: Vitest (unit), Playwright (e2e)

## Expected Dev Commands

Once scaffolded, commands will follow this pattern:

```bash
npm run dev          # start Vite dev server on :5173
npm run build        # tsc + vite build
npm run lint         # eslint
npm run type-check   # tsc --noEmit
npm run test         # vitest
npm run test:e2e     # playwright test
```

## Backend Integration

API base: `http://localhost:8000` (proxy through Vite to avoid CORS in dev)

**Auth flow**: `POST /auth/token` with `{ email, password, tenant_slug }` → returns Bearer JWT. All `/api/v1/...` routes require `Authorization: Bearer <token>`. The legacy endpoint `/api/v1/auth/login` does not require `tenant_slug` — new work should use `/auth/token`.

**Roles**: `staff` < `manager` < `platform_admin`. Gate UI elements by role fetched from `GET /auth/me`.

Key endpoint groups: Auth, Conversations, Messages, Suggested Replies, Inbox, Tasks, Escalations, Documents, RAG, Audit Logs. Full spec is in [backend-endpoints.md](backend-endpoints.md).

## Page Routes

| Route                    | Page                                                         |
| ------------------------ | ------------------------------------------------------------ |
| `/login`                 | Tenant-aware login (must include `tenant_slug` field)        |
| `/`                      | Overview — inbox summary, open tasks, open escalations       |
| `/inbox`                 | Conversation list with filters                               |
| `/inbox/:conversationId` | Conversation detail — messages, AI reply, tasks, escalations |
| `/documents`             | Document list, upload, archive                               |
| `/tasks`                 | Task list                                                    |
| `/escalations`           | Escalation list                                              |
| `/audit-logs`            | Audit log table (manager+)                                   |
| `/evaluation`            | Simulator demo                                               |

**Missing high-priority flows** (see [frontend-needed-pages.md](frontend-needed-pages.md)):

1. Outbound message sending on conversation detail (`POST /api/v1/conversations/{id}/messages`)
2. New conversation creation (`POST /api/v1/conversations`)
3. Tenant-slug login (`POST /auth/token`)

## Design System

Full spec in [DESIGN.md](DESIGN.md). Key values:

**Core colors** (use Tailwind CSS variables, not hardcoded hex):

- Primary: `#172033` (Midnight Navy) — buttons, nav, headings
- Secondary: `#A58F7A` (Warm Taupe)
- Accent: `#C8A96A` (Champagne Gold) — focus rings, selected states
- Background: `#FBF7EF` (Warm Ivory)
- Surface: `#FFFFFF`

**Semantic**:

- Success: `#2F7D5B` | Warning: `#B7791F` | Danger: `#A33A3A` | Info: `#3B6F8F`

**Border radius**: buttons/inputs `12px`, cards `16px`, modals `20px`

**Typography**: Newsreader for display/headline (`display-lg` 48px, `headline-lg` 32px); Inter for everything else. Body: 16px/24px. Labels: 14px medium.

**Spacing**: 8px base grid.

## Architecture Conventions

**API layer**: Centralized Axios instance with a Bearer token request interceptor and a 401 response interceptor that triggers token refresh or redirects to `/login`. React Query hooks wrap all data fetching — no raw `fetch`/`axios` calls in components.

**Auth context**: Zustand store holds `user`, `token`, and `tenant`. Populated on app load by calling `GET /auth/me`. Protected routes redirect to `/login` if no token.

**Component structure**:

- `src/components/` — reusable, domain-specific UI pieces
- `src/pages/` — route-level components (thin; delegate to components)
- `src/services/` — API functions (one file per domain)
- `src/hooks/` — React Query hooks (one file per domain)
- `src/store/` — Zustand slices
- `src/types/` — TypeScript interfaces matching backend Pydantic schemas

**Tone**: The interface should feel calm, premium, and structured — not flashy. Prefer subtle shadows, warm neutrals, and clear hierarchy over bright colors or decorative elements.
