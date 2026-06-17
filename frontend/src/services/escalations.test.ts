import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  api: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

import { api } from './api'
import { escalationsService } from './escalations'

const mockedGet = vi.mocked(api.get)
const mockedPatch = vi.mocked(api.patch)

describe('escalationsService', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPatch.mockReset()
    mockedGet.mockResolvedValue({ data: [] } as never)
    mockedPatch.mockResolvedValue({ data: { id: 'escalation-1', status: 'in_review' } } as never)
  })

  it('queries open escalations with the backend status value', async () => {
    await escalationsService.list({ status: 'open' })

    expect(mockedGet).toHaveBeenCalledWith('/api/v1/escalations', {
      params: { status: 'open' },
    })
  })

  it('queries acknowledged escalations as in_review', async () => {
    await escalationsService.list({ status: 'in_review' })

    expect(mockedGet).toHaveBeenCalledWith('/api/v1/escalations', {
      params: { status: 'in_review' },
    })
  })

  it('queries resolved escalations with the backend status value', async () => {
    await escalationsService.list({ status: 'resolved' })

    expect(mockedGet).toHaveBeenCalledWith('/api/v1/escalations', {
      params: { status: 'resolved' },
    })
  })

  it('updates an escalation to acknowledged using in_review', async () => {
    await escalationsService.update('escalation-1', { status: 'in_review' })

    expect(mockedPatch).toHaveBeenCalledWith('/api/v1/escalations/escalation-1', {
      status: 'in_review',
    })
  })
})
