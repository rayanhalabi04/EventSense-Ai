import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { m } from 'framer-motion'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { useEscalations, useUpdateEscalation } from '../hooks/useEscalations'
import { EscalationStatusBadge, RiskBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { formatRelative } from '../utils/date'
import { apiErrorDetail } from '../utils/apiError'
import { ESCALATION_FILTER_TABS, ESCALATION_STATUS_OPTIONS } from '../utils/escalationStatus'
import { useAuthStore } from '../store/authStore'
import type { EscalationStatus } from '../types'
import {
  escalationMeta,
  escalationReason,
  formatEscalationTitle,
  humanizeIntentLabel,
} from '../utils/workflowDisplay'

export function EscalationsPage() {
  const [searchParams] = useSearchParams()
  const selectedEscalationId = searchParams.get('escalationId')
  const [statusFilter, setStatusFilter] = useState<EscalationStatus | undefined>(() => (selectedEscalationId ? undefined : 'open'))
  const selectedEscalationRef = useRef<HTMLDivElement | null>(null)
  const user = useAuthStore((s) => s.user)
  const isManager = user?.role === 'manager' || user?.role === 'platform_admin'

  const escalations = useEscalations({ status: statusFilter })
  const updateEscalation = useUpdateEscalation()
  const errorDetail = import.meta.env.DEV ? apiErrorDetail(escalations.error) : undefined

  useEffect(() => {
    if (selectedEscalationId) setStatusFilter(undefined)
  }, [selectedEscalationId])

  useEffect(() => {
    if (!selectedEscalationId || !escalations.data?.some((esc) => esc.id === selectedEscalationId)) return
    selectedEscalationRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    selectedEscalationRef.current?.focus({ preventScroll: true })
  }, [selectedEscalationId, escalations.data])

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
        {ESCALATION_FILTER_TABS.map((tab) => (
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
        <ErrorState
          message="Could not load escalations."
          detail={errorDetail}
          onRetry={escalations.refetch}
        />
      ) : !escalations.data?.length ? (
        <EmptyState
          title="No escalations"
          description="No escalations match the current filter."
          icon={<AlertTriangle className="w-6 h-6" />}
        />
      ) : (
        <div className="space-y-3">
          {escalations.data.map((esc, i) => {
            const isSelected = selectedEscalationId === esc.id

            return (
              <m.div
                key={esc.id}
                ref={isSelected ? selectedEscalationRef : undefined}
                tabIndex={isSelected ? -1 : undefined}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className={`card p-5 scroll-mt-24 transition-colors focus:outline-none ${
                  isSelected
                    ? 'bg-accent-soft/40 border-accent/60 ring-2 ring-accent/40'
                    : 'hover:bg-surface-warm'
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-danger-soft text-danger flex items-center justify-center flex-shrink-0">
                    <AlertTriangle className="w-5 h-5" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1.5">
                          <p className="text-base font-semibold text-text-primary leading-snug">
                            {formatEscalationTitle(esc)}
                          </p>
                          {esc.risk_level && <RiskBadge level={esc.risk_level} />}
                          <EscalationStatusBadge status={esc.status} />
                        </div>
                        <p className="text-xs text-text-muted">{escalationMeta(esc)}</p>
                      </div>

                      {isManager && (
                        <select
                          value={esc.status}
                          onChange={(e) => handleStatusChange(esc.id, e.target.value as EscalationStatus)}
                          aria-label={`Change status for escalation: ${formatEscalationTitle(esc)}`}
                          className="text-xs border border-border rounded-md px-2 py-1.5 text-text-muted bg-surface hover:bg-surface-warm transition-colors focus:outline-none flex-shrink-0"
                        >
                          {ESCALATION_STATUS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    <div className="mt-4 rounded-lg border border-border bg-surface px-4 py-3">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                        {humanizeIntentLabel(esc.intent_label)}
                      </p>
                      <p className="text-sm text-text-primary leading-relaxed mt-1">
                        {escalationReason(esc)}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-xs text-text-muted mt-4">
                      <span>Created {formatRelative(esc.created_at)}</span>
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
                </div>
              </m.div>
            )
          })}
        </div>
      )}
    </div>
  )
}
