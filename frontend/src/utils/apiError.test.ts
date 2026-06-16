import { describe, expect, it } from 'vitest'
import { apiErrorDetail } from './apiError'

describe('apiErrorDetail', () => {
  it('returns undefined for no error', () => {
    expect(apiErrorDetail(undefined)).toBeUndefined()
    expect(apiErrorDetail(null)).toBeUndefined()
  })

  it('formats HTTP status with string detail', () => {
    const err = { response: { status: 500, data: { detail: 'boom' } } }
    expect(apiErrorDetail(err)).toBe('HTTP 500 — boom')
  })

  it('formats HTTP status alone when no detail body', () => {
    const err = { response: { status: 404, data: {} } }
    expect(apiErrorDetail(err)).toBe('HTTP 404')
  })

  it('serializes a non-string detail payload', () => {
    const err = { response: { status: 422, data: { detail: [{ msg: 'bad' }] } } }
    expect(apiErrorDetail(err)).toBe('HTTP 422 — [{"msg":"bad"}]')
  })

  it('falls back to the error message for network errors', () => {
    expect(apiErrorDetail(new Error('Network Error'))).toBe('Network Error')
  })
})
