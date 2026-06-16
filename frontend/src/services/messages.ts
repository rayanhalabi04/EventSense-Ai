import { api } from './api'
import type { Message, CreateMessageRequest } from '../types'

export const messagesService = {
  list: async (conversationId: string): Promise<Message[]> => {
    const res = await api.get<Message[]>(`/api/v1/conversations/${conversationId}/messages`)
    return res.data
  },

  create: async (conversationId: string, data: CreateMessageRequest): Promise<Message> => {
    const res = await api.post<Message>(`/api/v1/conversations/${conversationId}/messages`, data)
    return res.data
  },
}
