import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, CheckCircle, Link as LinkIcon, Unplug } from 'lucide-react'
import { useCalendarStatus, useConnectCalendar, useDisconnectCalendar } from '../hooks/useCalendar'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { ErrorState } from '../components/ui/ErrorState'
import { apiErrorDetail } from '../utils/apiError'

export function SettingsPage() {
  const [params] = useSearchParams()
  const calendarResult = params.get('calendar')
  const status = useCalendarStatus()
  const connect = useConnectCalendar()
  const disconnect = useDisconnectCalendar()
  const connectError = apiErrorDetail(connect.error)
  const disconnectError = apiErrorDetail(disconnect.error)

  const banner = useMemo(() => {
    if (calendarResult === 'connected') return 'Google Calendar connected'
    if (calendarResult === 'error') return 'Google Calendar connection failed'
    return null
  }, [calendarResult])

  const handleConnect = () => {
    connect.mutate(undefined, {
      onSuccess: (data) => {
        window.location.href = data.authorization_url
      },
    })
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-medium text-text-primary">Settings</h1>
        <p className="mt-0.5 text-sm text-text-muted">Agency integrations and workspace controls</p>
      </div>

      {banner && (
        <div className={`mb-5 rounded-lg border px-4 py-3 text-sm ${
          calendarResult === 'connected'
            ? 'border-success/20 bg-success-soft text-success'
            : 'border-danger/20 bg-danger-soft text-danger'
        }`}>
          {banner}
        </div>
      )}

      {status.isLoading ? (
        <PageLoader />
      ) : status.isError ? (
        <ErrorState onRetry={status.refetch} message="Could not load settings." />
      ) : (
        <section className="max-w-2xl rounded-lg border border-border bg-surface p-5 shadow-card">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
              <CalendarDays className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-base font-semibold text-text-primary">Google Calendar</h2>
                  {status.data?.connected ? (
                    <p className="mt-1 text-sm text-text-muted">
                      Connected as {status.data.provider_account_email}
                    </p>
                  ) : (
                    <p className="mt-1 text-sm text-text-muted">
                      Connect one shared Google Calendar for this agency.
                    </p>
                  )}
                </div>
                {status.data?.connected ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success">
                    <CheckCircle className="h-3.5 w-3.5" />
                    Connected
                  </span>
                ) : null}
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                {status.data?.connected ? (
                  <button
                    type="button"
                    onClick={() => disconnect.mutate()}
                    disabled={disconnect.isPending}
                    className="btn-secondary"
                  >
                    <Unplug className="h-4 w-4" />
                    {disconnect.isPending ? 'Disconnecting...' : 'Disconnect'}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleConnect}
                    disabled={connect.isPending}
                    className="btn-primary"
                  >
                    <LinkIcon className="h-4 w-4" />
                    {connect.isPending ? 'Opening...' : 'Connect Google Calendar'}
                  </button>
                )}
              </div>
              {(connectError || disconnectError) && (
                <p className="mt-3 text-xs text-danger">{connectError || disconnectError}</p>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
