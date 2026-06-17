import { describe, expect, it } from 'vitest'
import { DOCUMENT_TYPE_OPTIONS, documentTypeLabel } from './documentTypes'

describe('document type options', () => {
  it('uses backend enum values for displayed policy choices', () => {
    expect(DOCUMENT_TYPE_OPTIONS).toContainEqual({
      value: 'deposit_policy',
      label: 'Deposit policy',
    })
    expect(DOCUMENT_TYPE_OPTIONS).toContainEqual({
      value: 'cancellation_policy',
      label: 'Cancellation policy',
    })
    expect(DOCUMENT_TYPE_OPTIONS.map((option) => option.value)).not.toContain('policy')
  })

  it('formats backend enum values for display', () => {
    expect(documentTypeLabel('contract_terms')).toBe('Contract terms')
  })
})
