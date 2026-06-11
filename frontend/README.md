# EventSense AI — Frontend

A modern, professional SaaS dashboard for **EventSense AI**, the AI operations
assistant for wedding planners and event agencies. Staff can triage client
messages classified by intent and risk, review AI‑suggested replies (grounded in
tenant documents), create follow‑up tasks, escalate risky cases to managers, and
audit every action — with humans always in control.

## Tech stack

- **React 18 + TypeScript + Vite 5**
- **Tailwind CSS** with a custom EventSense design system
- **shadcn/ui‑style components** built on **Radix UI** primitives
- **TanStack Query** for data fetching/caching
- **React Router** for navigation
- **motion** for subtle route transitions
- **Biome** (format + lint) and **Knip** (unused files/deps)
- **lucide-react** icons, **sonner** toasts

## Getting started

```bash
cd frontend
npm install
cp .env.example .env      # adjust VITE_API_URL if your backend isn't on :8000
npm run dev               # http://localhost:5173
```

The backend must be running and seeded with demo data.

**Demo credentials**

| Tenant            | Email                          | Password          |
| ----------------- | ------------------------------ | ----------------- |
| Elegant Weddings  | `admin@elegant-weddings.demo`  | `demo-password-1` |
| Royal Events      | `admin@royal-events.demo`      | `demo-password-2` |

## Scripts

| Command             | Description                                   |
| ------------------- | --------------------------------------------- |
| `npm run dev`       | Start the Vite dev server                     |
| `npm run build`     | Type-check (`tsc -b`) and build for production |
| `npm run preview`   | Preview the production build                   |
| `npm run typecheck` | TypeScript project check                       |
| `npm run lint`      | Biome check (format + lint)                    |
| `npm run fix`       | Biome check with autofix                       |
| `npm run knip`      | Report unused files/exports/deps               |

## Configuration

- `VITE_API_URL` — base URL of the EventSense AI backend (default
  `http://localhost:8000`). The API client attaches the bearer token from
  local storage on every request.

The backend enables CORS for `http://localhost:5173` and `http://localhost:4173`
by default (configurable via the `CORS_ALLOW_ORIGINS` env var on the backend).

## Project structure

```
src/
  components/
    ui/         shadcn-style primitives (button, card, badge, dialog, …)
    layout/     AppShell, Sidebar, Topbar, PageHeader, BrandMark, nav
    common/     StatCard, DataTable, ActionButton, Empty/Error/Loading states
    badges/     IntentBadge, RiskBadge, StatusBadge
    domain/     MessageCard, AIReplyCard, SourceCard, AuditTimeline, DemoMetricCard
  hooks/        use-auth (auth context), queries (TanStack Query hooks)
  lib/          api client, types (backend contract mirrors), format helpers
  pages/        login, overview, inbox, message-detail, documents, tasks,
                escalations, audit-logs, evaluation
```

## Pages

1. **Login** — branded split-screen sign-in with clear error/loading states.
2. **Overview** — summary stat cards, recent messages, and a risk distribution bar.
3. **Inbox** — searchable, filterable table (status/risk/intent); high-risk rows stand out.
4. **Message detail** — full thread, AI assessment, risk reason, retrieved RAG
   sources, the suggested-reply card, and staff actions (approve/edit/copy/reject,
   create task, escalate). AI never auto-sends.
5. **Documents** — tenant knowledge base with type filter, search, and upload (managers).
6. **Tasks** — follow-up task cards with status tabs and overdue highlighting.
7. **Escalations** — manager review queue with start-review / resolve actions.
8. **Audit Logs** — readable timeline/table of AI + staff actions (managers).
9. **Evaluation / Demo** — live classifier demo via the simulator, plus evaluation
   suite cards (classifier, RAG, guardrails, tenant isolation).

## Backend integration notes

This frontend talks only to existing API endpoints; no contracts were changed.
A few intentional behaviours worth knowing:

- **"Mark as resolved"** on the message detail page is a documented placeholder —
  the current API has no conversation-status update endpoint. Resolution is
  modelled through tasks and escalations instead.
- **Intent/risk inbox filters** are applied client-side on the loaded page (the
  `/inbox` endpoint filters by status and search only).
- **Audit logs** and **document upload/archive** require manager/admin roles; the
  UI hides or gracefully degrades those affordances for staff users.
