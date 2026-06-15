import { useState } from 'react'
import { Link } from 'react-router-dom'
import { m } from 'framer-motion'
import { Search, Plus } from 'lucide-react'
import { useInbox } from '../hooks/useInbox'
import { useCreateConversation } from '../hooks/useConversations'
import { RiskBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { formatRelative } from '../utils/date'
import type { ConversationStatus } from '../types'

const STATUS_TABS: { label: string; value: ConversationStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Open', value: 'open' },
  { label: 'Pending', value: 'pending' },
  { label: 'Escalated', value: 'escalated' },
  { label: 'Resolved', value: 'resolved' },
]

export function InboxPage() {
  const [activeStatus, setActiveStatus] = useState<ConversationStatus | undefined>(undefined)
  const [search, setSearch] = useState('')
  const [showNewConvo, setShowNewConvo] = useState(false)
  const [newName, setNewName] = useState('')

  const inbox = useInbox({ status: activeStatus })
  const createConvo = useCreateConversation()

  const filtered = inbox.data?.filter((c) =>
    !search || (c.client_name ?? '').toLowerCase().includes(search.toLowerCase())
  )

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim()) return
    createConvo.mutate({ client_name: newName.trim(), source: 'manual' }, {
      onSuccess: () => { setShowNewConvo(false); setNewName('') },
    })
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-medium text-text-primary">Inbox</h1>
          <p className="text-sm text-text-muted mt-0.5">All client conversations</p>
        </div>
        <button type="button" onClick={() => setShowNewConvo(true)} className="btn-primary gap-1.5">
          <Plus className="w-4 h-4" />
          New conversation
        </button>
      </div>

      {/* New conversation modal */}
      {showNewConvo && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setShowNewConvo(false) }}
        >
          <m.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-surface rounded-xl border border-border shadow-modal p-6 w-full max-w-md"
          >
            <h2 className="text-base font-semibold text-text-primary mb-4">New conversation</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label htmlFor="convo-client-name" className="block text-xs font-medium text-text-primary mb-1.5">Client name</label>
                <input
                  id="convo-client-name"
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Sophia & James Carter"
                  className="input-base"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button type="submit" disabled={createConvo.isPending} className="btn-primary flex-1">
                  {createConvo.isPending ? 'Creating…' : 'Create conversation'}
                </button>
                <button type="button" onClick={() => setShowNewConvo(false)} className="btn-secondary">
                  Cancel
                </button>
              </div>
            </form>
          </m.div>
        </m.div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search by client name…"
            aria-label="Search conversations by client name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-base pl-9"
          />
        </div>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-5 bg-surface-warm border border-border rounded-lg p-1 w-fit">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => setActiveStatus(tab.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              activeStatus === tab.value
                ? 'bg-surface text-text-primary shadow-sm'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Conversation list */}
      {inbox.isLoading ? (
        <PageLoader />
      ) : inbox.isError ? (
        <ErrorState onRetry={inbox.refetch} />
      ) : !filtered?.length ? (
        <EmptyState
          title="No conversations"
          description="No conversations match the current filters."
        />
      ) : (
        <div className="card divide-y divide-border">
          {filtered.map((conv, i) => {
            const clientName = conv.client_name?.trim() || 'Unknown client'
            return (
              <m.div
                key={conv.conversation_id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.03 }}
              >
                <Link
                  to={`/inbox/${conv.conversation_id}`}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-surface-warm transition-colors"
                >
                  {/* Avatar */}
                  <div className="w-10 h-10 rounded-full bg-primary/8 border border-border flex items-center justify-center flex-shrink-0">
                    <span className="text-[11px] font-semibold text-text-primary">
                      {getInitials(clientName)}
                    </span>
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="text-sm font-medium text-text-primary truncate">{clientName}</p>
                      <RiskBadge level={conv.risk_level} />
                      {conv.intent_label && (
                        <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-surface-high text-text-muted">
                          {formatIntent(conv.intent_label)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-muted truncate">
                      {conv.message_preview || 'No messages yet'}
                    </p>
                    <p className="text-[11px] text-text-muted mt-0.5">
                      {conv.source ?? 'unknown source'}
                    </p>
                  </div>

                  {/* Meta */}
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBadgeClass(conv.status)}`}>
                      {conv.status ?? 'unknown'}
                    </span>
                    <span className="text-[11px] text-text-muted">{formatRelative(conv.latest_message_at)}</span>
                  </div>
                </Link>
              </m.div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function getInitials(name: string) {
  const initials = name
    .split(' ')
    .map((n) => n[0])
    .filter(Boolean)
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return initials || '?'
}

function formatIntent(label: string) {
  return label.replace(/_/g, ' ')
}

function statusBadgeClass(status: string | null | undefined) {
  switch (status) {
    case 'open': return 'bg-info-soft text-info'
    case 'escalated': return 'bg-danger-soft text-danger'
    case 'pending': return 'bg-warning-soft text-warning'
    case 'resolved': return 'bg-success-soft text-success'
    default: return 'bg-surface-high text-text-muted'
  }
}
