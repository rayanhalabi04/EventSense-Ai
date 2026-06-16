import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('./api', () => ({
  api: { post: vi.fn() },
}))

import { api } from './api'
import { telegramService } from './telegram'

const mockedPost = vi.mocked(api.post)

describe('telegramService.sendReply', () => {
  beforeEach(() => {
    mockedPost.mockReset()
    mockedPost.mockResolvedValue({
      data: {
        ok: true,
        message_id: 'm1',
        telegram_message_id: '42',
        conversation_id: 'c1',
      },
    } as never)
  })

  it('POSTs to /send-telegram-reply (not PATCH /suggested-replies)', async () => {
    await telegramService.sendReply('c1', { text: 'Hello', suggested_reply_id: 'r1' })

    expect(mockedPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockedPost.mock.calls[0]
    expect(url).toBe('/api/v1/conversations/c1/send-telegram-reply')
    expect(body).toEqual({ text: 'Hello', suggested_reply_id: 'r1' })
  })

  it('returns the parsed response data', async () => {
    const res = await telegramService.sendReply('c1', { text: 'Hi' })
    expect(res).toEqual({
      ok: true,
      message_id: 'm1',
      telegram_message_id: '42',
      conversation_id: 'c1',
    })
  })
})
