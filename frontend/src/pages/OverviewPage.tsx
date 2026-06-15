import { m } from 'framer-motion'
import { MessageSquare, CheckSquare, AlertTriangle, TrendingUp, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useInboxSummary } from '../hooks/useInbox'
import { useTasks } from '../hooks/useTasks'
import { useEscalations } from '../hooks/useEscalations'
import { useConversations } from '../hooks/useConversations'
import { useAuthStore } from '../store/authStore'
import { RiskBadge, TaskStatusBadge, EscalationStatusBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { formatRelative } from '../utils/date'

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { duration: 0.4, delay: i * 0.07 } }),
}

export function OverviewPage() {
  const user = useAuthStore((s) => s.user)
  const summary = useInboxSummary()
  const tasks = useTasks({ status: 'open' })
  const escalations = useEscalations({ status: 'open' })
  const conversations = useConversations()

  const isLoading = summary.isLoading || tasks.isLoading || escalations.isLoading || conversations.isLoading

  if (isLoading) return <PageLoader />

  const stats = [
    {
      label: 'Open conversations',
      value: summary.data?.open_count ?? 0,
      icon: MessageSquare,
      color: 'text-info',
      bg: 'bg-info-soft',
      to: '/inbox',
    },
    {
      label: 'Pending tasks',
      value: tasks.data?.length ?? 0,
      icon: CheckSquare,
      color: 'text-warning',
      bg: 'bg-warning-soft',
      to: '/tasks',
    },
    {
      label: 'Open escalations',
      value: escalations.data?.length ?? 0,
      icon: AlertTriangle,
      color: 'text-danger',
      bg: 'bg-danger-soft',
      to: '/escalations',
    },
    {
      label: 'High risk messages',
      value: summary.data?.high_risk_count ?? 0,
      icon: TrendingUp,
      color: 'text-danger',
      bg: 'bg-danger-soft',
      to: '/inbox',
    },
  ]
  const recentConversations = conversations.data ?? []

  return (
    <div>
      {/* Page header */}
      <div className="mb-8">
        <h1 className="font-display text-3xl font-medium text-text-primary">
          Good {getTimeOfDay()}, {user?.full_name?.split(' ')[0] ?? 'there'}
        </h1>
        <p className="text-sm text-text-muted mt-1">Here's what needs your attention today.</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((stat, i) => (
          <m.div
            key={stat.label}
            custom={i}
            variants={cardVariants}
            initial="hidden"
            animate="show"
          >
            <Link
              to={stat.to}
              className="block card p-5 hover:shadow-card-hover transition-shadow group"
            >
              <div className={`w-9 h-9 rounded-lg ${stat.bg} flex items-center justify-center mb-3`}>
                <stat.icon className={`w-4.5 h-4.5 ${stat.color}`} strokeWidth={1.75} />
              </div>
              <p className="text-2xl font-semibold text-text-primary">{stat.value}</p>
              <p className="text-xs text-text-muted mt-0.5">{stat.label}</p>
            </Link>
          </m.div>
        ))}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Recent conversations */}
        <div className="lg:col-span-3 card">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">Recent conversations</h2>
            <Link to="/inbox" className="text-xs text-text-muted hover:text-accent flex items-center gap-1">
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="divide-y divide-border">
            {recentConversations.slice(0, 6).map((conv) => {
              const clientName = conv.client_name || 'Unknown client'

              return (
                <Link
                  key={conv.id}
                  to={`/inbox/${conv.id}`}
                  className="flex items-center gap-3 px-5 py-3.5 hover:bg-surface-warm transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-primary/8 border border-border flex items-center justify-center flex-shrink-0">
                    <span className="text-[9px] font-semibold text-text-primary">
                      {getInitials(clientName)}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-text-primary truncate">{clientName}</p>
                    <p className="text-[10px] text-text-muted">{conv.source || 'Unknown source'}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <RiskBadge level={conv.risk_level} />
                    <span className="text-[10px] text-text-muted">{formatRelative(conv.last_message_at)}</span>
                  </div>
                </Link>
              )
            })}
            {!recentConversations.length && (
              <p className="px-5 py-8 text-sm text-text-muted text-center">No conversations yet.</p>
            )}
          </div>
        </div>

        {/* Tasks + Escalations */}
        <div className="lg:col-span-2 space-y-5">
          {/* Open tasks */}
          <div className="card">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">Open tasks</h2>
              <Link to="/tasks" className="text-xs text-text-muted hover:text-accent flex items-center gap-1">
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="divide-y divide-border">
              {tasks.data?.slice(0, 4).map((task) => (
                <div key={task.id} className="px-5 py-3 flex items-start gap-3">
                  <TaskStatusBadge status={task.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-text-primary truncate">{task.title}</p>
                    {task.due_date && (
                      <p className="text-[10px] text-text-muted">Due {formatRelative(task.due_date)}</p>
                    )}
                  </div>
                </div>
              ))}
              {!tasks.data?.length && (
                <p className="px-5 py-5 text-xs text-text-muted text-center">No open tasks.</p>
              )}
            </div>
          </div>

          {/* Open escalations */}
          <div className="card">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">Escalations</h2>
              <Link to="/escalations" className="text-xs text-text-muted hover:text-accent flex items-center gap-1">
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="divide-y divide-border">
              {escalations.data?.slice(0, 3).map((esc) => (
                <div key={esc.id} className="px-5 py-3 flex items-start gap-3">
                  <EscalationStatusBadge status={esc.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-text-primary truncate">{esc.title}</p>
                    <p className="text-[10px] text-text-muted capitalize">{esc.severity} severity</p>
                  </div>
                </div>
              ))}
              {!escalations.data?.length && (
                <p className="px-5 py-5 text-xs text-text-muted text-center">No open escalations.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function getTimeOfDay() {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}

function getInitials(name: string) {
  return name.split(' ').map((n) => n[0]).join('').slice(0, 2)
}
