import { Link } from 'react-router-dom'
import { AnimatePresence, m } from 'framer-motion'
import {
  ArrowLeft, Send, Sparkles, CheckCircle, XCircle, Clock, CheckCheck, CalendarDays,
} from 'lucide-react'
import { RiskBadge, TaskStatusBadge, EscalationStatusBadge } from '../components/ui/Badge'
import { formatDateTime, formatRelative } from '../utils/date'
import { autoReplySkipLabel, isAutoReplyMessage } from '../utils/suggestedReply'
import type { CalendarAvailabilityResponse, ConversationDetail, Message, SuggestedReply } from '../types'

export type ConversationTab = 'tasks' | 'escalations' | 'audit'
export type AsyncStatus = 'idle' | 'pending'
export type ReplyChannel = 'telegram' | 'manual'

interface ConversationHeaderProps {
  conv: ConversationDetail
  source: string
  messageCount: number
  onCreateCalendarEvent?: () => void
}

export function ConversationHeader({ conv, source, messageCount, onCreateCalendarEvent }: ConversationHeaderProps) {
  return (
    <div className="flex items-center gap-3 mb-4 flex-shrink-0">
      <Link to="/inbox" className="p-2 hover:bg-surface-warm rounded-lg transition-colors">
        <ArrowLeft className="w-4 h-4 text-text-muted" />
      </Link>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-text-primary truncate">{conv.client_name || 'Unknown client'}</h1>
          {conv.latest_risk_level && <RiskBadge level={conv.latest_risk_level} />}
        </div>
        <p className="text-xs text-text-muted">{source} &middot; {messageCount} messages &middot; {conv.conversation_status}</p>
      </div>
      {onCreateCalendarEvent && (
        <button type="button" onClick={onCreateCalendarEvent} className="btn-secondary flex-shrink-0">
          <CalendarDays className="h-4 w-4" />
          Create Calendar Event
        </button>
      )}
    </div>
  )
}

interface MessageThreadProps {
  messages: Message[]
  messagesEndRef: React.Ref<HTMLDivElement>
}

function MessageThread({ messages, messagesEndRef }: MessageThreadProps) {
  return (
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
  )
}

interface SuggestedReplyCardProps {
  conv: ConversationDetail
  pendingReply: SuggestedReply | null
  replyError: string | null
  generationStatus: AsyncStatus
  replyChannel: ReplyChannel
  telegramReplyStatus: AsyncStatus
  dismissStatus: AsyncStatus
  onUseReply: (pending: SuggestedReply) => void
  onDismissReply: (pending: SuggestedReply) => void
}

function SuggestedReplyCard({
  conv,
  pendingReply,
  replyError,
  generationStatus,
  replyChannel,
  telegramReplyStatus,
  dismissStatus,
  onUseReply,
  onDismissReply,
}: SuggestedReplyCardProps) {
  const isGenerating = generationStatus === 'pending'
  const isSendingTelegram = telegramReplyStatus === 'pending'
  const autoReplySkipMessage = autoReplySkipLabel(conv.auto_reply_skip_reason)

  return (
    <AnimatePresence>
      {(pendingReply || isGenerating) && (
        <m.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="border-t border-border px-4 py-3 bg-accent-soft/50"
        >
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-3.5 h-3.5 text-accent" />
            <span className="text-xs font-semibold text-text-primary">AI suggested reply</span>
            {import.meta.env.DEV && autoReplySkipMessage && (
              <span className="text-[10px] text-text-muted">
                ({autoReplySkipMessage})
              </span>
            )}
          </div>
          {isGenerating ? (
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
                  onClick={() => onUseReply(pendingReply)}
                  disabled={isSendingTelegram}
                  className="flex items-center gap-1.5 text-xs font-medium text-success hover:text-success/80 transition-colors disabled:opacity-50"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  {isSendingTelegram && replyChannel === 'telegram' ? 'Sending…' : 'Use this reply'}
                </button>
                <button
                  type="button"
                  onClick={() => onDismissReply(pendingReply)}
                  disabled={dismissStatus === 'pending'}
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
  )
}

function CalendarAvailabilityCard({ availability }: { availability?: CalendarAvailabilityResponse | null }) {
  if (!availability) return null

  const status =
    availability.available === true
      ? { label: 'Available', className: 'text-success', Icon: CheckCircle }
      : availability.available === false
        ? { label: 'Busy', className: 'text-danger', Icon: XCircle }
        : { label: 'Unknown', className: 'text-text-muted', Icon: Clock }
  const StatusIcon = status.Icon

  return (
    <div className="border-t border-border px-4 py-3 bg-surface">
      <div className="flex items-center gap-2 mb-2">
        <CalendarDays className="w-3.5 h-3.5 text-accent" />
        <span className="text-xs font-semibold text-text-primary">Calendar availability</span>
      </div>
      <div className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">Requested</span>
          <span className="text-text-primary text-right">
            {availability.requested_start_time
              ? formatDateTime(availability.requested_start_time)
              : 'Needs preferred time'}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">Status</span>
          <span className={`inline-flex items-center gap-1 font-medium ${status.className}`}>
            <StatusIcon className="w-3.5 h-3.5" />
            {status.label}
          </span>
        </div>
        {availability.reason && availability.available !== true && (
          <div className="flex items-center justify-between gap-3">
            <span className="text-text-muted">Reason</span>
            <span className="text-text-primary text-right capitalize">
              {availability.reason.replace(/_/g, ' ')}
            </span>
          </div>
        )}
        {availability.alternatives?.length ? (
          <div className="pt-1">
            <p className="text-text-muted mb-1">Alternatives</p>
            <div className="space-y-1">
              {availability.alternatives.map((slot) => (
                <p key={`${slot.start_time}-${slot.end_time}`} className="text-text-primary">
                  {formatDateTime(slot.start_time)}
                </p>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

interface MessageComposerProps {
  message: string
  sendStatus: AsyncStatus
  generationStatus: AsyncStatus
  onMessageChange: (message: string) => void
  onSend: (e: React.FormEvent) => void
  onGenerateReply: () => void
}

function MessageComposer({
  message,
  sendStatus,
  generationStatus,
  onMessageChange,
  onSend,
  onGenerateReply,
}: MessageComposerProps) {
  return (
    <div className="border-t border-border p-3">
      <form onSubmit={onSend} className="flex gap-2">
        <div className="flex-1 relative">
          <textarea
            value={message}
            onChange={(e) => onMessageChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(e) } }}
            placeholder="Type a reply…"
            rows={2}
            aria-label="Type a reply"
            className="input-base resize-none text-sm py-2 pr-10"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <button
            type="submit"
            disabled={!message.trim() || sendStatus === 'pending'}
            className="btn-primary p-2.5 disabled:opacity-50"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={onGenerateReply}
            disabled={generationStatus === 'pending'}
            className="p-2.5 border border-border bg-surface hover:bg-surface-warm text-text-muted hover:text-accent rounded-md transition-colors"
            aria-label="Generate AI reply"
            title="Generate AI reply"
          >
            <Sparkles className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  )
}

interface ConversationMainPanelProps {
  conv: ConversationDetail
  messages: Message[]
  messagesEndRef: React.Ref<HTMLDivElement>
  message: string
  pendingReply: SuggestedReply | null
  replyError: string | null
  replyChannel: ReplyChannel
  messageSendStatus: AsyncStatus
  replyGenerationStatus: AsyncStatus
  telegramReplyStatus: AsyncStatus
  replyDismissStatus: AsyncStatus
  onMessageChange: (message: string) => void
  onSend: (e: React.FormEvent) => void
  onGenerateReply: () => void
  onUseReply: (pending: SuggestedReply) => void
  onDismissReply: (pending: SuggestedReply) => void
}

export function ConversationMainPanel({
  conv,
  messages,
  messagesEndRef,
  message,
  pendingReply,
  replyError,
  replyChannel,
  messageSendStatus,
  replyGenerationStatus,
  telegramReplyStatus,
  replyDismissStatus,
  onMessageChange,
  onSend,
  onGenerateReply,
  onUseReply,
  onDismissReply,
}: ConversationMainPanelProps) {
  return (
    <div className="flex-1 flex flex-col card overflow-hidden">
      <MessageThread messages={messages} messagesEndRef={messagesEndRef} />
      <CalendarAvailabilityCard availability={conv.calendar_availability} />
      <SuggestedReplyCard
        conv={conv}
        pendingReply={pendingReply}
        replyError={replyError}
        generationStatus={replyGenerationStatus}
        replyChannel={replyChannel}
        telegramReplyStatus={telegramReplyStatus}
        dismissStatus={replyDismissStatus}
        onUseReply={onUseReply}
        onDismissReply={onDismissReply}
      />
      <MessageComposer
        message={message}
        sendStatus={messageSendStatus}
        generationStatus={replyGenerationStatus}
        onMessageChange={onMessageChange}
        onSend={onSend}
        onGenerateReply={onGenerateReply}
      />
    </div>
  )
}

interface ConversationSidebarProps {
  conv: ConversationDetail
  source: string
  messageCount: number
  activeTab: ConversationTab
  onTabChange: (tab: ConversationTab) => void
}

export function ConversationSidebar({
  conv,
  source,
  messageCount,
  activeTab,
  onTabChange,
}: ConversationSidebarProps) {
  return (
    <div className="w-72 flex-shrink-0 flex flex-col gap-4 overflow-y-auto">
      <div className="card flex-shrink-0">
        <div className="flex border-b border-border">
          {(['tasks', 'escalations', 'audit'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => onTabChange(tab)}
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
          {activeTab === 'tasks' && <TasksPanel conv={conv} />}
          {activeTab === 'escalations' && <EscalationsPanel conv={conv} />}
          {activeTab === 'audit' && <AuditPanel conv={conv} />}
        </div>
      </div>
      <ConversationMeta conv={conv} source={source} messageCount={messageCount} />
    </div>
  )
}

function TasksPanel({ conv }: { conv: ConversationDetail }) {
  return (
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
  )
}

function EscalationsPanel({ conv }: { conv: ConversationDetail }) {
  return (
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
  )
}

function AuditPanel({ conv }: { conv: ConversationDetail }) {
  return (
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
  )
}

function ConversationMeta({
  conv,
  source,
  messageCount,
}: ConversationHeaderProps) {
  return (
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
        <span className="text-text-primary">{messageCount}</span>
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
  )
}
