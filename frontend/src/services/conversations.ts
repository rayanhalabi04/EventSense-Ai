import { api } from './api'
import type { Conversation, ConversationDetail } from '../types'

export const conversationsService = {
  list: async (): Promise<Conversation[]> => {
    const res = await api.get<Conversation[]>('/api/v1/conversations')
    return res.data
  },

  get: async (id: string): Promise<Conversation> => {
    const res = await api.get<Conversation>(`/api/v1/conversations/${id}`)
    return res.data
  },

  detail: async (id: string): Promise<ConversationDetail> => {
    const res = await api.get<ConversationDetail>(`/api/v1/conversations/${id}/detail`)
    return res.data
  },

  create: async (data: { client_name: string; client_phone?: string; source?: string }): Promise<Conversation> => {
    const res = await api.post<Conversation>('/api/v1/conversations', data)
    return res.data
  },
}
