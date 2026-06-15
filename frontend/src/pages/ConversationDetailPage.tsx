import { useState, useRef, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { AnimatePresence, m } from 'framer-motion'
import {
  ArrowLeft, Send, Sparkles, CheckCircle, XCircle, Clock,
} from 'lucide-react'
import { useConversationDetail, useSendMessage, useGenerateReply } from '../hooks/useConversations'
import { RiskBadge, TaskStatusBadge, EscalationStatusBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { ErrorState } from '../components/ui/ErrorState'
import { formatDateTime, formatRelative } from '../utils/date'

export function ConversationDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const [message, setMessage] = useState('')
  const [activeTab, setActiveTab] = useState<'tasks' | 'escalations' | 'audit'>('tasks')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const detail = useConversationDetail(conversationId ?? '')
  const sendMessage = useSendMessage(conversationId ?? '')
  const generateReply = useGenerateReply(conversationId ?? '')

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [detail.data?.messages])

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return
    sendMessage.mutate({ content: message.trim(), direction: 'outbound' }, {
      onSuccess: () => setMessage(''),
    })
  }

  const handleGenerateReply = () => generateReply.mutate()

  if (detail.isLoading) return <PageLoader />
  if (detail.isError) return <ErrorState onRetry={detail.refetch} message="Could not load conversation." />

  const conv = detail.data!
  const pendingReply = conv.suggested_replies?.find((r) => r.status === 'pending')

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 flex-shrink-0">
        <Link to="/inbox" className="p-2 hover:bg-surface-warm rounded-lg transition-colors">
          <ArrowLeft className="w-4 h-4 text-text-muted" />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-text-primary truncate">{conv.client_name}</h1>
            <RiskBadge level={conv.risk_level} />
          </div>
          <p className="text-xs text-text-muted">{conv.source} &middot; {conv.message_count} messages &middot; {conv.status}</p>
        </div>
      </div>

      <div className="flex gap-5 flex-1 min-h-0">
        {/* Left: Message thread */}
        <div className="flex-1 flex flex-col card overflow-hidden">
          {/* Messages scroll area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {conv.messages?.map((msg) => (
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
                  {msg.intent && msg.direction === 'inbound' && (
                    <div className="flex items-center gap-1 mb-1">
                      <span className="text-[9px] font-semibold uppercase tracking-widest text-text-muted">
                        {msg.intent.replace(/_/g, ' ')}
                      </span>
                    </div>
                  )}
                  <p className="text-sm leading-relaxed">{msg.content}</p>
                  <p className={`text-[10px] mt-1 ${msg.direction === 'outbound' ? 'text-white/50' : 'text-text-muted'}`}>
                    {formatDateTime(msg.created_at)}
                  </p>
                </div>
              </m.div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* AI suggested reply */}
          <AnimatePresence>
            {(pendingReply || generateReply.isPending) && (
              <m.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="border-t border-border bg-accent-soft/50 px-4 py-3"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-3.5 h-3.5 text-accent" />
                  <span className="text-xs font-semibold text-text-primary">AI suggested reply</span>
                </div>
                {generateReply.isPending ? (
                  <div className="h-8 flex items-center gap-2 text-xs text-text-muted">
                    <div className="w-3 h-3 border border-accent border-t-transparent rounded-full animate-spin" />
                    Generating reply…
                  </div>
                ) : pendingReply ? (
                  <>
                    <p className="text-sm text-text-body leading-relaxed mb-2">{pendingReply.content}</p>
                    {pendingReply.rag_sources?.length ? (
                      <p className="text-[10px] text-text-muted mb-2">
                        Based on: {pendingReply.rag_sources.map((s) => s.title).join(', ')}
                      </p>
                    ) : null}
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setMessage(pendingReply.content)}
                        className="flex items-center gap-1.5 text-xs font-medium text-success hover:text-success/80 transition-colors"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        Use this reply
                      </button>
                      <button type="button" className="flex items-center gap-1.5 text-xs font-medium text-danger hover:text-danger/80 transition-colors">
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
                      {task.due_date && (
                        <p className="text-[10px] text-text-muted flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatRelative(task.due_date)}
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
                        <p className="text-xs font-medium text-text-primary leading-snug">{esc.title}</p>
                        <EscalationStatusBadge status={esc.status} />
                      </div>
                      <p className="text-[10px] text-text-muted capitalize">{esc.severity} severity</p>
                    </div>
                  )) : (
                    <p className="text-xs text-text-muted text-center py-4">No escalations for this conversation.</p>
                  )}
                </div>
              )}

              {activeTab === 'audit' && (
                <div className="space-y-2">
                  {conv.audit_events?.length ? conv.audit_events.map((ev) => (
                    <div key={ev.id} className="flex gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent mt-1.5 flex-shrink-0" />
                      <div>
                        <p className="text-xs text-text-primary">{ev.action}</p>
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
              <span className="text-text-primary font-medium">{conv.source}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Created</span>
              <span className="text-text-primary">{formatRelative(conv.created_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Messages</span>
              <span className="text-text-primary">{conv.message_count}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
