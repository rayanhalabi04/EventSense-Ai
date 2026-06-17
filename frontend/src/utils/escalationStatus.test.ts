import { describe, expect, it } from 'vitest'
import {
  ESCALATION_FILTER_TABS,
  ESCALATION_STATUS_OPTIONS,
  getEscalationStatusLabel,
} from './escalationStatus'

describe('escalation status display', () => {
  it('maps the Acknowledged filter label to the backend in_review status', () => {
    expect(ESCALATION_FILTER_TABS.find((tab) => tab.label === 'Acknowledged')?.value).toBe(
      'in_review',
    )
  })

  it('uses backend status values for the status dropdown', () => {
    expect(ESCALATION_STATUS_OPTIONS).toContainEqual({
      label: 'Acknowledged',
      value: 'in_review',
    })
  })

  it('displays human labels for escalation cards', () => {
    expect(getEscalationStatusLabel('open')).toBe('Open')
    expect(getEscalationStatusLabel('in_review')).toBe('Acknowledged')
    expect(getEscalationStatusLabel('resolved')).toBe('Resolved')
  })
})
