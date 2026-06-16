import { api } from './api'

export interface SendTelegramReplyRequest {
  text: string
  /** Id of the AI suggested reply being sent, so the backend can mark it used. */
  suggested_reply_id?: string
}

export interface SendTelegramReplyResponse {
  ok: boolean
  message_id: string
  telegram_message_id?: string | null
  conversation_id: string
}

export const telegramService = {
  /**
   * Actually deliver a reply to the Telegram client (and persist the outbound
   * message). This is the endpoint "Use this reply" must call for Telegram
   * conversations — NOT PATCH /suggested-replies, which only updates status.
   */
  sendReply: async (
    conversationId: string,
    data: SendTelegramReplyRequest,
  ): Promise<SendTelegramReplyResponse> => {
    const res = await api.post<SendTelegramReplyResponse>(
      `/api/v1/conversations/${conversationId}/send-telegram-reply`,
      data,
    )
    return res.data
  },
}
