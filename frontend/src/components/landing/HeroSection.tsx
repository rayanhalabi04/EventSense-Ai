import { Link } from 'react-router-dom'
import { m } from 'framer-motion'
import { ArrowRight, MessageSquare, CheckSquare, AlertTriangle } from 'lucide-react'

const dashboardPreviewItems = [
  { label: 'Sofía & Marco wedding', risk: 'high', intent: 'Guest count change', time: '2m ago', initials: 'SM' },
  { label: 'Chen Corporate Gala', risk: 'low', intent: 'Confirmation', time: '15m ago', initials: 'CG' },
  { label: 'Rivera Quinceañera', risk: 'critical', intent: 'Cancellation risk', time: '32m ago', initials: 'RQ' },
  { label: 'The Laurent Anniversary', risk: 'medium', intent: 'Payment inquiry', time: '1h ago', initials: 'LA' },
]

const riskColors: Record<string, string> = {
  low: 'bg-success-soft text-success',
  medium: 'bg-warning-soft text-warning',
  high: 'bg-danger-soft text-danger',
  critical: 'bg-danger-soft text-danger',
}

export function HeroSection() {
  return (
    <section className="relative pt-32 pb-20 overflow-hidden bg-bg-warm">
      {/* Decorative background elements */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-20 right-0 w-[600px] h-[600px] rounded-full bg-accent/5 blur-3xl" />
        <div className="absolute bottom-0 left-1/4 w-[400px] h-[400px] rounded-full bg-primary/3 blur-3xl" />
        {/* Grid lines */}
        <svg className="absolute inset-0 w-full h-full opacity-[0.03]" aria-hidden>
          <defs>
            <pattern id="grid" width="64" height="64" patternUnits="userSpaceOnUse">
              <path d="M 64 0 L 0 0 0 64" fill="none" stroke="#172033" strokeWidth="1"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      <div className="relative max-w-6xl mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          {/* Left: Text content */}
          <div>
            <m.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent-soft border border-accent/20 rounded-full mb-6"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-accent" />
              <span className="text-xs font-medium text-text-accent">Built for professional event teams</span>
            </m.div>

            <m.h1
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="font-display text-5xl lg:text-6xl font-medium text-text-primary leading-[1.1] tracking-tight mb-6"
            >
              Every client message,{' '}
              <em className="not-italic text-accent">organized</em>{' '}
              and acted on.
            </m.h1>

            <m.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="text-lg text-text-muted leading-relaxed mb-8 max-w-lg"
            >
              EventSense turns scattered WhatsApp messages and client inquiries into structured workflows — detecting risks, creating tasks, and suggesting professional replies so your team never misses what matters.
            </m.p>

            <m.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="flex flex-wrap gap-3"
            >
              <Link to="/login" className="btn-primary px-6 py-3 text-base gap-2">
                Start organizing
                <ArrowRight className="w-4 h-4" />
              </Link>
              <a href="#how-it-works" className="btn-secondary px-6 py-3 text-base">
                See how it works
              </a>
            </m.div>

            <m.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.5 }}
              className="mt-10 flex items-center gap-6 text-sm text-text-muted"
            >
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-accent" />
                <span>Smart inbox</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckSquare className="w-4 h-4 text-accent" />
                <span>Auto tasks</span>
              </div>
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-accent" />
                <span>Risk alerts</span>
              </div>
            </m.div>
          </div>

          {/* Right: Dashboard preview */}
          <m.div
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="relative"
          >
            {/* Outer glow */}
            <div className="absolute -inset-4 bg-gradient-to-br from-accent/10 to-primary/5 rounded-2xl blur-xl" />

            <div className="relative bg-surface rounded-xl border border-border shadow-modal overflow-hidden">
              {/* Dashboard header */}
              <div className="flex items-center gap-2 px-4 py-3 bg-primary/3 border-b border-border">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-danger/40" />
                  <div className="w-2.5 h-2.5 rounded-full bg-warning/40" />
                  <div className="w-2.5 h-2.5 rounded-full bg-success/40" />
                </div>
                <div className="mx-auto flex items-center gap-1.5 px-3 py-0.5 bg-surface-warm rounded text-[10px] text-text-muted font-medium border border-border">
                  <span>eventsense.app</span>
                </div>
              </div>

              {/* Summary stats */}
              <div className="grid grid-cols-3 gap-px bg-border p-px mx-4 mt-4 rounded-lg overflow-hidden">
                {[
                  { label: 'Open threads', value: '24' },
                  { label: 'Pending tasks', value: '8' },
                  { label: 'Escalations', value: '2' },
                ].map((stat) => (
                  <div key={stat.label} className="bg-surface px-3 py-2.5 text-center">
                    <p className="text-lg font-semibold text-text-primary">{stat.value}</p>
                    <p className="text-[10px] text-text-muted mt-0.5">{stat.label}</p>
                  </div>
                ))}
              </div>

              {/* Conversation list */}
              <div className="p-4 space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-3">Recent conversations</p>
                {dashboardPreviewItems.map((item, i) => (
                  <m.div
                    key={item.label}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.4, delay: 0.4 + i * 0.08 }}
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-surface-warm transition-colors cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-full bg-primary/8 border border-border flex items-center justify-center flex-shrink-0">
                      <span className="text-[9px] font-semibold text-text-primary">{item.initials}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-text-primary truncate">{item.label}</p>
                      <p className="text-[10px] text-text-muted truncate">{item.intent}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full ${riskColors[item.risk]}`}>
                        {item.risk}
                      </span>
                      <span className="text-[10px] text-text-muted">{item.time}</span>
                    </div>
                  </m.div>
                ))}
              </div>
            </div>
          </m.div>
        </div>
      </div>
    </section>
  )
}
