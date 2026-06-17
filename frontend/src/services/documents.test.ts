import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from './api'
import { documentsService } from './documents'

const mockedPost = vi.mocked(api.post)

describe('documentsService', () => {
  beforeEach(() => {
    mockedPost.mockReset()
    mockedPost.mockResolvedValue({
      data: {
        id: 'doc-1',
        title: 'Deposit policy',
        document_type: 'deposit_policy',
        status: 'active',
      },
    } as never)
  })

  it('uploads .txt documents to the multipart upload endpoint', async () => {
    const file = new File(['Deposit terms'], 'deposit-policy.txt', { type: 'text/plain' })

    await documentsService.upload(file, 'deposit_policy', 'Deposit policy')

    expect(mockedPost).toHaveBeenCalledTimes(1)
    const [url, body, config] = mockedPost.mock.calls[0]
    expect(url).toBe('/api/v1/documents/upload')
    expect(config).toBeUndefined()
    expect(body).toBeInstanceOf(FormData)
    const form = body as FormData
    expect(form.get('file')).toBe(file)
    expect(form.get('document_type')).toBe('deposit_policy')
    expect(form.get('title')).toBe('Deposit policy')
  })
})
