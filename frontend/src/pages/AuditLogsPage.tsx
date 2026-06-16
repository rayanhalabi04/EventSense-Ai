import { useState } from 'react'
import { ClipboardList, Search } from 'lucide-react'
import { useAuditLogs } from '../hooks/useAuditLogs'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { formatDateTime } from '../utils/date'

const PAGE_SIZE = 50

export function AuditLogsPage() {
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')

  const logs = useAuditLogs({ limit: PAGE_SIZE, offset })

  const filtered = logs.data?.filter(
    (l) => !search || l.action.toLowerCase().includes(search.toLowerCase()) || l.resource_type?.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-medium text-text-primary">Audit Logs</h1>
        <p className="text-sm text-text-muted mt-0.5">Complete activity history for your organization</p>
      </div>

      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          placeholder="Filter by action or resource type…"
          aria-label="Filter audit logs by action or resource type"
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
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Action</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Resource</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-text-muted">Resource ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((log) => (
                    <tr key={log.id} className="hover:bg-surface-warm transition-colors">
                      <td className="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                        {formatDateTime(log.created_at)}
                      </td>
                      <td className="px-4 py-3 text-xs font-medium text-text-primary">{log.action}</td>
                      <td className="px-4 py-3 text-xs text-text-muted">{log.resource_type ?? '—'}</td>
                      <td className="px-4 py-3 text-xs text-text-muted font-mono">
                        {log.resource_id ? log.resource_id.slice(0, 8) + '…' : '—'}
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
