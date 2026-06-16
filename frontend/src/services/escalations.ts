import { api } from './api'
import type { Escalation, UpdateEscalationRequest, EscalationStatus } from '../types'

export const escalationsService = {
  list: async (filters?: { status?: EscalationStatus; conversation_id?: string }): Promise<Escalation[]> => {
    const res = await api.get<Escalation[]>('/api/v1/escalations', { params: filters })
    return res.data
  },

  get: async (id: string): Promise<Escalation> => {
    const res = await api.get<Escalation>(`/api/v1/escalations/${id}`)
    return res.data
  },

  update: async (id: string, data: UpdateEscalationRequest): Promise<Escalation> => {
    const res = await api.patch<Escalation>(`/api/v1/escalations/${id}`, data)
    return res.data
  },
}
