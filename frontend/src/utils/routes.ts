import type { InboxMessage } from '../types'

/**
 * Canonical path for a conversation detail page. The detail route is keyed by
 * the *conversation* id (a UUID) — never a message id — and the detail page
 * fetches `GET /api/v1/conversations/{conversationId}/detail`.
 */
export function conversationDetailPath(conversationId: string): string {
  return `/inbox/${conversationId}`
}

/**
 * Build the detail link for an inbox row. Inbox rows carry both a
 * `conversation_id` and a `latest_message_id`; navigation must use
 * `conversation_id` so the detail endpoint receives a conversation UUID (using
 * the message id would 404/500). Centralised here so the rule is enforced and
 * tested in one place.
 */
export function inboxRowDetailPath(
  row: Pick<InboxMessage, 'conversation_id'>,
): string {
  return conversationDetailPath(row.conversation_id)
}
