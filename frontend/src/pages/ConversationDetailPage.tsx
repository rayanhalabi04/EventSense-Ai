import { useState, useRef, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { AnimatePresence, m } from 'framer-motion'
import {
  ArrowLeft, Send, Sparkles, CheckCircle, XCircle, Clock, CheckCheck,
} from 'lucide-react'
import {
  useConversationDetail,
  useSendMessage,
  useGenerateReply,
  useSendTelegramReply,
  useDismissSuggestedReply,
} from '../hooks/useConversations'
import { RiskBadge, TaskStatusBadge, EscalationStatusBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { ErrorState } from '../components/ui/ErrorState'
import { formatDateTime, formatRelative } from '../utils/date'
import { getSuggestedReplyCardState, isAutoReplyMessage } from '../utils/suggestedReply'
import { apiErrorDetail } from '../utils/apiError'
import type { SuggestedReply } from '../types'

export function ConversationDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const [message, setMessage] = useState('')
  const [activeTab, setActiveTab] = useState<'tasks' | 'escalations' | 'audit'>('tasks')
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
  // Only a *pending* (draft, not-yet-sent) suggestion needs the action card.
  // Auto-sent replies are already shown as outbound bubbles in the thread, so we
  // never render a separate card for them.
  const reply = conv.suggested_reply
  const replyCard = getSuggestedReplyCardState(reply)
  const pendingReply = replyCard.kind === 'pending' ? reply : null

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
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 flex-shrink-0">
        <Link to="/inbox" className="p-2 hover:bg-surface-warm rounded-lg transition-colors">
          <ArrowLeft className="w-4 h-4 text-text-muted" />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-text-primary truncate">{conv.client_name || 'Unknown client'}</h1>
            {conv.latest_risk_level && <RiskBadge level={conv.latest_risk_level} />}
          </div>
          <p className="text-xs text-text-muted">{source} &middot; {messages.length} messages &middot; {conv.conversation_status}</p>
        </div>
      </div>

      <div className="flex gap-5 flex-1 min-h-0">
        {/* Left: Message thread */}
        <div className="flex-1 flex flex-col card overflow-hidden">
          {/* Messages scroll area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <p className="text-sm text-text-muted">No messages in this conversation yet.</p>
              </div>
            ) : (
              messages.map((msg) => (
                <m.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[75%] rounded-xl px-4 py-2.5 ${
                      msg.direction === 'outbound'
                        ? 'bg-primary text-white rounded-br-sm'
                        : 'bg-surface-warm border border-border text-text-body rounded-bl-sm'
                    }`}
                  >
                    {msg.intent_label && msg.direction === 'inbound' && (
                      <div className="flex items-center gap-1 mb-1">
                        <span className="text-[9px] font-semibold uppercase tracking-widest text-text-muted">
                          {msg.intent_label.replace(/_/g, ' ')}
                        </span>
                      </div>
                    )}
                    <p className={`text-sm leading-relaxed whitespace-pre-wrap ${msg.body ? '' : 'italic opacity-60'}`}>
                      {msg.body || 'No message body'}
                    </p>
                    {isAutoReplyMessage(msg) && (
                      <span className="mt-1 inline-flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wide text-white/70">
                        <CheckCheck className="w-3 h-3" />
                        Auto-replied via Telegram
                      </span>
                    )}
                    <p className={`text-[10px] mt-1 ${msg.direction === 'outbound' ? 'text-white/50' : 'text-text-muted'}`}>
                      {formatDateTime(msg.sent_at)}
                    </p>
                  </div>
                </m.div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* AI suggested reply — only for a pending draft awaiting human review.
              Auto-sent replies are already shown as outbound bubbles above. */}
          <AnimatePresence>
            {(pendingReply || generateReply.isPending) && (
              <m.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="border-t border-border px-4 py-3 bg-accent-soft/50"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-3.5 h-3.5 text-accent" />
                  <span className="text-xs font-semibold text-text-primary">AI suggested reply</span>
                  {import.meta.env.DEV && conv.auto_reply_skip_reason && (
                    <span className="text-[10px] text-text-muted font-mono">
                      (auto-reply skipped: {conv.auto_reply_skip_reason})
                    </span>
                  )}
                </div>
                {generateReply.isPending ? (
                  <div className="h-8 flex items-center gap-2 text-xs text-text-muted">
                    <div className="w-3 h-3 border border-accent border-t-transparent rounded-full animate-spin" />
                    Generating reply…
                  </div>
                ) : pendingReply ? (
                  <>
                    <p className="text-sm text-text-body leading-relaxed mb-2 whitespace-pre-wrap">{pendingReply.suggested_text}</p>
                    {pendingReply.rag_sources?.length ? (
                      <p className="text-[10px] text-text-muted mb-2">
                        Based on: {pendingReply.rag_sources.map((s) => s.document_title).join(', ')}
                      </p>
                    ) : null}
                    {replyError && (
                      <p className="text-[10px] text-danger mb-2">{replyError}</p>
                    )}
                    <div className="flex gap-3">
                      <button
                        type="button"
                        onClick={() => handleUseReply(pendingReply)}
                        disabled={sendTelegramReply.isPending}
                        className="flex items-center gap-1.5 text-xs font-medium text-success hover:text-success/80 transition-colors disabled:opacity-50"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        {sendTelegramReply.isPending && isTelegram ? 'Sending…' : 'Use this reply'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDismissReply(pendingReply)}
                        disabled={dismissReply.isPending}
                        className="flex items-center gap-1.5 text-xs font-medium text-danger hover:text-danger/80 transition-colors disabled:opacity-50"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        Dismiss
                      </button>
                    </div>
                  </>
                ) : null}
              </m.div>
            )}
          </AnimatePresence>

          {/* Message input */}
          <div className="border-t border-border p-3">
            <form onSubmit={handleSend} className="flex gap-2">
              <div className="flex-1 relative">
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(e) } }}
                  placeholder="Type a reply…"
                  rows={2}
                  aria-label="Type a reply"
                  className="input-base resize-none text-sm py-2 pr-10"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <button
                  type="submit"
                  disabled={!message.trim() || sendMessage.isPending}
                  className="btn-primary p-2.5 disabled:opacity-50"
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleGenerateReply}
                  disabled={generateReply.isPending}
                  className="p-2.5 border border-border bg-surface hover:bg-surface-warm text-text-muted hover:text-accent rounded-md transition-colors"
                  aria-label="Generate AI reply"
                  title="Generate AI reply"
                >
                  <Sparkles className="w-4 h-4" />
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Right: Sidebar */}
        <div className="w-72 flex-shrink-0 flex flex-col gap-4 overflow-y-auto">
          {/* Tabs */}
          <div className="card flex-shrink-0">
            <div className="flex border-b border-border">
              {(['tasks', 'escalations', 'audit'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`flex-1 py-2.5 text-xs font-medium capitalize transition-colors ${
                    activeTab === tab
                      ? 'text-text-primary border-b-2 border-accent -mb-px'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  {tab === 'audit' ? 'Timeline' : tab}
                  {tab === 'tasks' && conv.tasks?.length ? (
                    <span className="ml-1.5 text-[10px] bg-surface-high text-text-muted rounded-full px-1.5 py-0.5">
                      {conv.tasks.length}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>

            <div className="p-3">
              {activeTab === 'tasks' && (
                <div className="space-y-2">
                  {conv.tasks?.length ? conv.tasks.map((task) => (
                    <div key={task.id} className="p-2.5 bg-surface-warm rounded-lg border border-border">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <p className="text-xs font-medium text-text-primary leading-snug">{task.title}</p>
                        <TaskStatusBadge status={task.status} />
                      </div>
                      {task.due_at && (
                        <p className="text-[10px] text-text-muted flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatRelative(task.due_at)}
                        </p>
                      )}
                    </div>
                  )) : (
                    <p className="text-xs text-text-muted text-center py-4">No tasks linked to this conversation.</p>
                  )}
                </div>
              )}

              {activeTab === 'escalations' && (
                <div className="space-y-2">
                  {conv.escalations?.length ? conv.escalations.map((esc) => (
                    <div key={esc.id} className="p-2.5 bg-surface-warm rounded-lg border border-border">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <p className="text-xs font-medium text-text-primary leading-snug">
                          {esc.ai_summary || esc.suggested_next_step || 'Escalation'}
                        </p>
                        <EscalationStatusBadge status={esc.status} />
                      </div>
                      {esc.risk_level && (
                        <p className="text-[10px] text-text-muted capitalize">{esc.risk_level} risk</p>
                      )}
                    </div>
                  )) : (
                    <p className="text-xs text-text-muted text-center py-4">No escalations for this conversation.</p>
                  )}
                </div>
              )}

              {activeTab === 'audit' && (
                <div className="space-y-2">
                  {conv.audit_timeline?.length ? conv.audit_timeline.map((ev) => (
                    <div key={ev.id} className="flex gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent mt-1.5 flex-shrink-0" />
                      <div>
                        <p className="text-xs text-text-primary">{ev.event_type.replace(/[._]/g, ' ')}</p>
                        <p className="text-[10px] text-text-muted">{formatDateTime(ev.created_at)}</p>
                      </div>
                    </div>
                  )) : (
                    <p className="text-xs text-text-muted text-center py-4">No audit events yet.</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Conversation meta */}
          <div className="card p-4 text-xs space-y-2 flex-shrink-0">
            <p className="font-semibold text-text-primary mb-2">Details</p>
            <div className="flex justify-between">
              <span className="text-text-muted">Source</span>
              <span className="text-text-primary font-medium capitalize">{source}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Created</span>
              <span className="text-text-primary">{formatRelative(conv.created_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Messages</span>
              <span className="text-text-primary">{messages.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Status</span>
              <span className="text-text-primary capitalize">{conv.conversation_status ?? 'unknown'}</span>
            </div>
            {conv.latest_risk_level && (
              <div className="flex justify-between">
                <span className="text-text-muted">Risk</span>
                <span className="text-text-primary capitalize">{conv.latest_risk_level}</span>
              </div>
            )}
            {conv.latest_intent_label && (
              <div className="flex justify-between">
                <span className="text-text-muted">Intent</span>
                <span className="text-text-primary capitalize">{conv.latest_intent_label.replace(/_/g, ' ')}</span>
              </div>
            )}
            {conv.client_contact && (
              <div className="flex justify-between">
                <span className="text-text-muted">Contact</span>
                <span className="text-text-primary truncate ml-2">{conv.client_contact}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
