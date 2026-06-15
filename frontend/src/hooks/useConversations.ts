import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conversationsService } from '../services/conversations'
import { messagesService } from '../services/messages'
import { suggestedRepliesService } from '../services/suggestedReplies'
import type { CreateMessageRequest } from '../types'

export function useConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: conversationsService.list,
  })
}

export function useConversationDetail(id: string) {
  return useQuery({
    queryKey: ['conversations', id, 'detail'],
    queryFn: () => conversationsService.detail(id),
    enabled: Boolean(id),
  })
}

export function useSendMessage(conversationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateMessageRequest) => messagesService.create(conversationId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations', conversationId] })
    },
  })
}

export function useGenerateReply(conversationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => suggestedRepliesService.generate(conversationId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations', conversationId] })
    },
  })
}

export function useCreateConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: conversationsService.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.invalidateQueries({ queryKey: ['inbox'] })
    },
  })
}
