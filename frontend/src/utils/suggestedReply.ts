import type { Message, SuggestedReply } from '../types'

/**
 * Decides how the conversation-detail "AI suggested reply" card should behave for
 * a given reply.
 *
 * - `auto_sent`: the reply was already delivered to the client automatically
 *   (e.g. a low-risk Telegram auto-reply). The dashboard shows it for
 *   transparency but must NOT ask staff to approve/dismiss it again.
 * - `pending`: a draft awaiting human approval — show the normal
 *   "Use this reply" / "Dismiss" actions.
 * - `hidden`: nothing actionable to show (no reply, or already resolved by a
 *   human via approve/edit/reject).
 */
export type SuggestedReplyCardKind = 'auto_sent' | 'pending' | 'hidden'

export interface SuggestedReplyCardState {
  kind: SuggestedReplyCardKind
  /** Channel the reply was auto-sent through, e.g. "telegram". */
  channel: string | null
}

const AUTO_REPLY_SKIP_LABELS: Record<string, string> = {
  rag_provider_unavailable: 'Auto-send skipped: document search was temporarily unavailable',
  embedding_provider_unavailable: 'Auto-send skipped: document search was temporarily unavailable',
  no_rag_source: 'Auto-send skipped: no supporting company document was found',
  guardrail_refusal: 'Auto-send skipped: safety rules require staff review',
  auto_reply_disabled: 'Auto-send skipped: Telegram auto-send is disabled',
  risk_not_low: 'Auto-send skipped: staff review is required for this risk level',
  blocked_intent: 'Auto-send skipped: staff review is required for this request',
  intent_not_allowed: 'Auto-send skipped: staff review is required for this request',
  risky_keyword: 'Auto-send skipped: staff review is required for this request',
  client_reply_empty: 'Auto-send skipped: the draft could not be prepared for Telegram',
  suggested_reply_empty: 'Auto-send skipped: the draft was empty',
  telegram_send_failed: 'Auto-send skipped: Telegram delivery failed',
}

export function autoReplySkipLabel(reason: string | null | undefined): string | null {
  if (!reason) return null
  return AUTO_REPLY_SKIP_LABELS[reason] ?? 'Auto-send skipped: staff review is required'
}

export function getSuggestedReplyCardState(
  reply: SuggestedReply | null | undefined,
): SuggestedReplyCardState {
  if (!reply) return { kind: 'hidden', channel: null }
  if (reply.auto_sent_at) {
    return { kind: 'auto_sent', channel: reply.sent_channel ?? 'telegram' }
  }
  if (reply.status === 'draft') {
    return { kind: 'pending', channel: null }
  }
  return { kind: 'hidden', channel: null }
}

/**
 * An auto-sent reply should have produced an outbound message in the thread.
 * The auto-reply text is reformatted before sending (prefixes/markdown stripped),
 * so we can't rely on an exact body match — the meaningful defensive signal is
 * simply whether any outbound message exists. If none does, the UI warns that the
 * reply was marked sent but no outbound message was found.
 */
export function hasOutboundMessage(messages: Message[] | null | undefined): boolean {
  return (messages ?? []).some((m) => m.direction === 'outbound')
}

/**
 * True when an outbound message was delivered to the client automatically by the
 * Telegram auto-reply pipeline (vs. sent by a staff member). Auto-replies are
 * persisted with no `sender_user_id`; staff sends always carry one. Used to show
 * a small "Auto-replied via Telegram" badge on the bubble instead of a separate
 * large suggested-reply card.
 */
export function isAutoReplyMessage(message: Message): boolean {
  return (
    message.direction === 'outbound' &&
    message.source === 'telegram' &&
    !message.sender_user_id
  )
}
