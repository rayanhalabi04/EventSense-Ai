import { api } from './api'
import type { SuggestedReply } from '../types'

export const suggestedRepliesService = {
  generate: async (conversationId: string): Promise<SuggestedReply> => {
    const res = await api.post<SuggestedReply>(`/api/v1/conversations/${conversationId}/suggested-reply`)
    return res.data
  },

  list: async (conversationId: string): Promise<SuggestedReply[]> => {
    const res = await api.get<SuggestedReply[]>(`/api/v1/conversations/${conversationId}/suggested-replies`)
    return res.data
  },

  update: async (replyId: string, data: { status?: string; content?: string }): Promise<SuggestedReply> => {
    const res = await api.patch<SuggestedReply>(`/api/v1/suggested-replies/${replyId}`, data)
    return res.data
  },
}
