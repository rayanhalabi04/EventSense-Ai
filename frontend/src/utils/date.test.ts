import { describe, expect, it } from 'vitest'
import { formatDate, formatDateTime, formatRelative } from './date'

describe('date utilities', () => {
  it('returns an empty string for empty date values', () => {
    expect(formatDate('')).toBe('')
    expect(formatDateTime('')).toBe('')
    expect(formatRelative('')).toBe('')
  })
})
