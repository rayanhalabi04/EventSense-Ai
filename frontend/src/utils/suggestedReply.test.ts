import { describe, expect, it } from 'vitest'
import {
  getSuggestedReplyCardState,
  hasOutboundMessage,
  isAutoReplyMessage,
} from './suggestedReply'
import type { Message, SuggestedReply } from '../types'

function makeReply(overrides: Partial<SuggestedReply> = {}): SuggestedReply {
  return {
    id: 'r1',
    tenant_id: 't1',
    conversation_id: 'c1',
    message_id: 'm1',
    suggested_text: 'Hi, our package starts at the published rate.',
    status: 'draft',
    source_document_ids: [],
    rag_sources: [],
    answer_supported: true,
    refusal_reason: null,
    generation_method: 'template_v1',
    auto_sent_at: null,
    sent_channel: null,
    created_by_user_id: null,
    approved_by_user_id: null,
    created_at: '2026-06-15T10:00:00Z',
    updated_at: '2026-06-15T10:00:00Z',
    ...overrides,
  }
}

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg1',
    tenant_id: 't1',
    conversation_id: 'c1',
    direction: 'inbound',
    status: 'read',
    body: 'Hello',
    sent_at: '2026-06-15T10:00:00Z',
    ...overrides,
  }
}

describe('getSuggestedReplyCardState', () => {
  it('hides the card when there is no reply', () => {
    expect(getSuggestedReplyCardState(null).kind).toBe('hidden')
    expect(getSuggestedReplyCardState(undefined).kind).toBe('hidden')
  })

  it('treats a draft reply as pending (shows approval actions)', () => {
    expect(getSuggestedReplyCardState(makeReply({ status: 'draft' })).kind).toBe('pending')
  })

  it('treats an auto-sent reply as auto_sent (no approval actions)', () => {
    const state = getSuggestedReplyCardState(
      makeReply({ status: 'draft', auto_sent_at: '2026-06-15T10:05:00Z', sent_channel: 'telegram' }),
    )
    expect(state.kind).toBe('auto_sent')
    expect(state.channel).toBe('telegram')
  })

  it('prefers auto_sent even if status is still draft', () => {
    const state = getSuggestedReplyCardState(
      makeReply({ status: 'draft', auto_sent_at: '2026-06-15T10:05:00Z', sent_channel: null }),
    )
    expect(state.kind).toBe('auto_sent')
    // Falls back to telegram when channel is not recorded.
    expect(state.channel).toBe('telegram')
  })

  it('hides the card for human-resolved replies', () => {
    expect(getSuggestedReplyCardState(makeReply({ status: 'approved' })).kind).toBe('hidden')
    expect(getSuggestedReplyCardState(makeReply({ status: 'rejected' })).kind).toBe('hidden')
  })
})

describe('isAutoReplyMessage', () => {
  it('is true for an outbound telegram message with no sender (auto-reply)', () => {
    const msg = makeMessage({
      direction: 'outbound',
      source: 'telegram',
      sender_user_id: null,
    })
    expect(isAutoReplyMessage(msg)).toBe(true)
  })

  it('is false for a staff-sent telegram message (has sender)', () => {
    const msg = makeMessage({
      direction: 'outbound',
      source: 'telegram',
      sender_user_id: 'user-1',
    })
    expect(isAutoReplyMessage(msg)).toBe(false)
  })

  it('is false for inbound telegram messages', () => {
    const msg = makeMessage({ direction: 'inbound', source: 'telegram', sender_user_id: null })
    expect(isAutoReplyMessage(msg)).toBe(false)
  })

  it('is false for non-telegram outbound messages', () => {
    const msg = makeMessage({ direction: 'outbound', source: 'simulator', sender_user_id: null })
    expect(isAutoReplyMessage(msg)).toBe(false)
  })
})

describe('hasOutboundMessage', () => {
  it('returns false when there are no outbound messages', () => {
    expect(hasOutboundMessage([])).toBe(false)
    expect(hasOutboundMessage([makeMessage({ direction: 'inbound' })])).toBe(false)
    expect(hasOutboundMessage(undefined)).toBe(false)
  })

  it('returns true when an outbound message exists', () => {
    expect(
      hasOutboundMessage([makeMessage({ direction: 'inbound' }), makeMessage({ direction: 'outbound' })]),
    ).toBe(true)
  })
})
