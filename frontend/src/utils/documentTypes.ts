import type { DocumentType } from '../types'

export const DOCUMENT_TYPE_OPTIONS: Array<{ value: DocumentType; label: string }> = [
  { value: 'pricing', label: 'Pricing' },
  { value: 'package', label: 'Package' },
  { value: 'faq', label: 'FAQ' },
  { value: 'deposit_policy', label: 'Deposit policy' },
  { value: 'cancellation_policy', label: 'Cancellation policy' },
  { value: 'contract_terms', label: 'Contract terms' },
  { value: 'service_description', label: 'Service description' },
  { value: 'decoration_rules', label: 'Decoration rules' },
  { value: 'catering_rules', label: 'Catering rules' },
  { value: 'other', label: 'Other' },
]

export function documentTypeLabel(value: DocumentType): string {
  return DOCUMENT_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? value
}
