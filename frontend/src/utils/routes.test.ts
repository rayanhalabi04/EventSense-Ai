import { describe, expect, it } from 'vitest'
import { conversationDetailPath, inboxRowDetailPath } from './routes'

describe('conversationDetailPath', () => {
  it('routes to /inbox/{conversationId}', () => {
    expect(conversationDetailPath('d822f689-6c18-47ef-8df8-3e4636a9638d')).toBe(
      '/inbox/d822f689-6c18-47ef-8df8-3e4636a9638d',
    )
  })
})

describe('inboxRowDetailPath', () => {
  it('uses conversation_id, not latest_message_id', () => {
    const row = {
      conversation_id: 'conv-uuid',
      latest_message_id: 'msg-uuid',
    }
    const path = inboxRowDetailPath(row)
    expect(path).toBe('/inbox/conv-uuid')
    expect(path).not.toContain('msg-uuid')
  })

  it('routes Telegram-source rows by conversation_id', () => {
    // A Telegram inbox row carries source="telegram" plus distinct ids; the
    // detail link must still key on the conversation id so the detail endpoint
    // receives a conversation UUID.
    const telegramRow = {
      conversation_id: 'd822f689-6c18-47ef-8df8-3e4636a9638d',
      latest_message_id: '11111111-2222-3333-4444-555555555555',
    }
    expect(inboxRowDetailPath(telegramRow)).toBe(
      '/inbox/d822f689-6c18-47ef-8df8-3e4636a9638d',
    )
  })
})
