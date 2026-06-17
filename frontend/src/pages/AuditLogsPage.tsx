import { useState } from 'react'
import { Activity, ClipboardList, Search } from 'lucide-react'
import { useAuditLogs } from '../hooks/useAuditLogs'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { Badge } from '../components/ui/Badge'
import { formatDateTime } from '../utils/date'
import {
  auditEventLabel,
  auditEventVariant,
  auditLogSearchText,
  auditLogSummary,
  auditResourceLabel,
  shortId,
} from '../utils/auditLog'

const PAGE_SIZE = 50

export function AuditLogsPage() {
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')

  const logs = useAuditLogs({ limit: PAGE_SIZE, offset })

  const normalizedSearch = search.trim().toLowerCase()
  const filtered = logs.data?.filter((log) => !normalizedSearch || auditLogSearchText(log).includes(normalizedSearch))

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-medium text-text-primary">Audit Logs</h1>
        <p className="text-sm text-text-muted mt-0.5">Transparent AI workflow history for your organization</p>
      </div>

      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          placeholder="Filter by event, resource, source, reason, or ID..."
          aria-label="Filter audit logs by event, resource, source, reason, or ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-base pl-9"
        />
      </div>

      {logs.isLoading ? (
        <PageLoader />
      ) : logs.isError ? (
        <ErrorState onRetry={logs.refetch} />
      ) : !filtered?.length ? (
        <EmptyState
          title="No audit logs"
          description="Audit events will appear here as your team takes actions."
          icon={<ClipboardList className="w-6 h-6" />}
        />
      ) : (
        <>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface-warm">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Time</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Event</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Summary</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Resource</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((log) => (
                    <tr key={log.id} className="hover:bg-surface-warm transition-colors">
                      <td className="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <Activity className="w-3.5 h-3.5 text-accent" />
                          {formatDateTime(log.created_at)}
                        </div>
                      </td>
                      <td className="px-4 py-3 min-w-56">
                        <Badge variant={auditEventVariant(log)}>{auditEventLabel(log)}</Badge>
                        <p className="mt-1 text-[11px] text-text-muted font-mono">{log.event_type || log.action}</p>
                      </td>
                      <td className="px-4 py-3 text-xs text-text-body min-w-80 max-w-xl">
                        {auditLogSummary(log)}
                      </td>
                      <td className="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                        <p className="font-medium text-text-primary">{auditResourceLabel(log.resource_type)}</p>
                        <p className="font-mono" title={log.resource_id ?? undefined}>
                          {shortId(log.resource_id) || '-'}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-xs text-text-muted min-w-48">
                        <details>
                          <summary className="cursor-pointer select-none text-text-accent font-medium">
                            View details
                          </summary>
                          <pre className="mt-2 max-w-md overflow-x-auto rounded-md bg-surface-high p-3 text-[11px] text-text-primary">
                            {JSON.stringify(
                              {
                                id: log.id,
                                actor_user_id: log.actor_user_id,
                                resource_id: log.resource_id,
                                details: log.details ?? {},
                              },
                              null,
                              2,
                            )}
                          </pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <p className="text-xs text-text-muted">
              Showing {offset + 1}–{offset + (filtered?.length ?? 0)}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))}
                disabled={offset === 0}
                className="btn-secondary text-xs py-1.5 px-3 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                type="button"
                onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
                disabled={(logs.data?.length ?? 0) < PAGE_SIZE}
                className="btn-secondary text-xs py-1.5 px-3 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
