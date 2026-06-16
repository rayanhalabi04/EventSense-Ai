import { useState } from 'react'
import { Link } from 'react-router-dom'
import { m } from 'framer-motion'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { useEscalations, useUpdateEscalation } from '../hooks/useEscalations'
import { EscalationStatusBadge, RiskBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { formatRelative } from '../utils/date'
import { useAuthStore } from '../store/authStore'
import type { EscalationStatus } from '../types'

const STATUS_TABS: { label: string; value: EscalationStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Open', value: 'open' },
  { label: 'Acknowledged', value: 'acknowledged' },
  { label: 'Resolved', value: 'resolved' },
]

export function EscalationsPage() {
  const [statusFilter, setStatusFilter] = useState<EscalationStatus | undefined>('open')
  const user = useAuthStore((s) => s.user)
  const isManager = user?.role === 'manager' || user?.role === 'platform_admin'

  const escalations = useEscalations({ status: statusFilter })
  const updateEscalation = useUpdateEscalation()

  const handleStatusChange = (id: string, status: EscalationStatus) => {
    updateEscalation.mutate({ id, data: { status } })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-medium text-text-primary">Escalations</h1>
          <p className="text-sm text-text-muted mt-0.5">Urgent situations requiring manager attention</p>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-1 mb-5 bg-surface-warm border border-border rounded-lg p-1 w-fit">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => setStatusFilter(tab.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              statusFilter === tab.value ? 'bg-surface text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {escalations.isLoading ? (
        <PageLoader />
      ) : escalations.isError ? (
        <ErrorState onRetry={escalations.refetch} />
      ) : !escalations.data?.length ? (
        <EmptyState
          title="No escalations"
          description="No escalations match the current filter."
          icon={<AlertTriangle className="w-6 h-6" />}
        />
      ) : (
        <div className="space-y-3">
          {escalations.data.map((esc, i) => (
            <m.div
              key={esc.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className="card p-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <p className="text-sm font-semibold text-text-primary">{esc.ai_summary || 'Escalation'}</p>
                    {esc.risk_level && <RiskBadge level={esc.risk_level} />}
                    <EscalationStatusBadge status={esc.status} />
                  </div>
                  {esc.suggested_next_step && (
                    <p className="text-sm text-text-muted mb-2">{esc.suggested_next_step}</p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-text-muted">
                    <span>{formatRelative(esc.created_at)}</span>
                    {esc.conversation_id && (
                      <Link
                        to={`/inbox/${esc.conversation_id}`}
                        className="flex items-center gap-1 text-accent hover:underline"
                      >
                        View conversation <ArrowRight className="w-3 h-3" />
                      </Link>
                    )}
                  </div>
                </div>

                {isManager && (
                  <select
                    value={esc.status}
                    onChange={(e) => handleStatusChange(esc.id, e.target.value as EscalationStatus)}
                    aria-label={`Change status for escalation: ${esc.ai_summary || esc.id}`}
                    className="text-xs border border-border rounded-md px-2 py-1.5 text-text-muted bg-surface hover:bg-surface-warm transition-colors focus:outline-none flex-shrink-0"
                  >
                    <option value="open">Open</option>
                    <option value="acknowledged">Acknowledge</option>
                    <option value="resolved">Resolve</option>
                    <option value="dismissed">Dismiss</option>
                  </select>
                )}
              </div>
            </m.div>
          ))}
        </div>
      )}
    </div>
  )
}
