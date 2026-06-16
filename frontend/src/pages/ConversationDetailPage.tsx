import { useState, useRef, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import {
  useConversationDetail,
  useSendMessage,
  useGenerateReply,
  useSendTelegramReply,
  useDismissSuggestedReply,
} from '../hooks/useConversations'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { ErrorState } from '../components/ui/ErrorState'
import { getSuggestedReplyCardState } from '../utils/suggestedReply'
import { apiErrorDetail } from '../utils/apiError'
import {
  ConversationHeader,
  ConversationMainPanel,
  ConversationSidebar,
  type AsyncStatus,
  type ConversationTab,
  type ReplyChannel,
} from './ConversationDetailSections'
import type { SuggestedReply } from '../types'

function mutationStatus(isPending: boolean): AsyncStatus {
  return isPending ? 'pending' : 'idle'
}

export function ConversationDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const [message, setMessage] = useState('')
  const [activeTab, setActiveTab] = useState<ConversationTab>('tasks')
  const [replyError, setReplyError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const detail = useConversationDetail(conversationId ?? '')
  const sendMessage = useSendMessage(conversationId ?? '')
  const generateReply = useGenerateReply(conversationId ?? '')
  const sendTelegramReply = useSendTelegramReply(conversationId ?? '')
  const dismissReply = useDismissSuggestedReply(conversationId ?? '')

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [detail.data?.messages])

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return
    sendMessage.mutate({ body: message.trim(), direction: 'outbound' }, {
      onSuccess: () => setMessage(''),
    })
  }

  const handleGenerateReply = () => generateReply.mutate()

  if (detail.isLoading) return <PageLoader />
  if (detail.isError) {
    // Surface the real status/detail while developing so failures like a 500 on
    // the detail endpoint are diagnosable instead of a blank "Could not load".
    const devDetail = import.meta.env.DEV ? apiErrorDetail(detail.error) : undefined
    return (
      <ErrorState
        onRetry={detail.refetch}
        message="Could not load conversation."
        detail={devDetail}
      />
    )
  }

  const conv = detail.data!
  const messages = conv.messages ?? []
  // The conversation source isn't a top-level field — take it from whichever
  // message carries one (e.g. "telegram"/"simulator").
  const source = messages.find((m) => m.source)?.source ?? 'Unknown source'
  const isTelegram = messages.some((m) => m.source === 'telegram')
  const replyChannel: ReplyChannel = isTelegram ? 'telegram' : 'manual'
  // Only a *pending* (draft, not-yet-sent) suggestion needs the action card.
  // Auto-sent replies are already shown as outbound bubbles in the thread, so we
  // never render a separate card for them.
  const reply = conv.suggested_reply
  const replyCard = getSuggestedReplyCardState(reply)
  const pendingReply = replyCard.kind === 'pending' ? reply ?? null : null

  const handleUseReply = (pending: SuggestedReply) => {
    setReplyError(null)
    if (isTelegram) {
      // Actually deliver it to the Telegram client and mark the suggestion used.
      sendTelegramReply.mutate(
        { text: pending.suggested_text, suggested_reply_id: pending.id },
        {
          onError: (err) =>
            setReplyError(apiErrorDetail(err) ?? 'Failed to send reply to Telegram.'),
        },
      )
    } else {
      // Non-Telegram conversations: keep existing behavior (load into the box).
      setMessage(pending.suggested_text)
    }
  }

  const handleDismissReply = (pending: SuggestedReply) => {
    setReplyError(null)
    dismissReply.mutate(pending.id)
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <ConversationHeader conv={conv} source={source} messageCount={messages.length} />
      <div className="flex gap-5 flex-1 min-h-0">
        <ConversationMainPanel
          conv={conv}
          messages={messages}
          messagesEndRef={messagesEndRef}
          message={message}
          pendingReply={pendingReply}
          replyError={replyError}
          replyChannel={replyChannel}
          messageSendStatus={mutationStatus(sendMessage.isPending)}
          replyGenerationStatus={mutationStatus(generateReply.isPending)}
          telegramReplyStatus={mutationStatus(sendTelegramReply.isPending)}
          replyDismissStatus={mutationStatus(dismissReply.isPending)}
          onMessageChange={setMessage}
          onSend={handleSend}
          onGenerateReply={handleGenerateReply}
          onUseReply={handleUseReply}
          onDismissReply={handleDismissReply}
        />
        <ConversationSidebar
          conv={conv}
          source={source}
          messageCount={messages.length}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />
      </div>
    </div>
  )
}
