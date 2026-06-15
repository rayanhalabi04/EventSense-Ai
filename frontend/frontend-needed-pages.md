# EventSense AI Frontend Page Needs

Source reviewed: `EventSense-Ai/frontend`

This file summarizes the current frontend pages and the pages or flows still needed to cover the backend API and expected operator workflows.

## Existing Pages

| Page                | Route                    | Current Coverage                                                                |
| ------------------- | ------------------------ | ------------------------------------------------------------------------------- |
| Login               | `/login`                 | Signs in through legacy `/api/v1/auth/login` and loads `/auth/me`               |
| Overview            | `/`                      | Inbox summary, open tasks, open escalations, recent messages, risk overview     |
| Inbox               | `/inbox`                 | Conversation list with status, risk, intent, and search filters                 |
| Conversation detail | `/inbox/:conversationId` | Messages, AI suggested replies, RAG sources, tasks, escalations, audit timeline |
| Documents           | `/documents`             | List, filter, upload, and archive tenant documents                              |
| Tasks               | `/tasks`                 | List tasks by status and update task status                                     |
| Escalations         | `/escalations`           | List escalations and allow managers/admins to update status                     |
| Audit logs          | `/audit-logs`            | Manager/admin audit log table with search                                       |
| Evaluation/demo     | `/evaluation`            | Live simulator message demo plus evaluation suite overview                      |
