import { m } from 'framer-motion'
import { Heart, Building2, Utensils, Flower2, CalendarDays } from 'lucide-react'

const segments = [
  {
    icon: Heart,
    title: 'Wedding planners',
    benefit: 'Manage dozens of client relationships simultaneously without missing a single detail, dietary restriction, or vendor deadline.',
  },
  {
    icon: Building2,
    title: 'Event agencies',
    benefit: 'Scale your team\'s capacity without adding headcount. EventSense handles the triage so your coordinators can focus on high-value work.',
  },
  {
    icon: Building2,
    title: 'Venue coordinators',
    benefit: 'Track client inquiries, booking confirmations, and last-minute changes across every event space — from a single operations view.',
  },
  {
    icon: Flower2,
    title: 'Decorators',
    benefit: 'Convert client vision boards and specification messages into clear, trackable briefs. No more chasing approval threads.',
  },
  {
    icon: Utensils,
    title: 'Caterers',
    benefit: 'Guest-count changes, dietary updates, and payment confirmations are detected immediately and routed to the right person.',
  },
  {
    icon: CalendarDays,
    title: 'Event managers',
    benefit: 'Get a real-time view of which events are on track, which have open risks, and which need escalation — without digging through messages.',
  },
]

export function BenefitsSection() {
  return (
    <section className="py-24 bg-bg-warm">
      <div className="max-w-6xl mx-auto px-6">
        <m.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mb-14"
        >
          <p className="section-label mb-4">Who it's for</p>
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
            <h2 className="font-display text-4xl font-medium text-text-primary leading-tight max-w-lg">
              Built for every role in the event industry
            </h2>
            <p className="text-base text-text-muted max-w-sm">
              Whether you run a boutique wedding studio or a large events agency, EventSense adapts to your workflow.
            </p>
          </div>
        </m.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-px bg-border rounded-xl overflow-hidden">
          {segments.map((seg, i) => (
            <m.div
              key={seg.title}
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
              className="bg-surface p-6 hover:bg-surface-warm transition-colors group"
            >
              <div className="w-9 h-9 rounded-lg bg-accent-soft border border-accent/20 flex items-center justify-center mb-4 group-hover:bg-accent/15 transition-colors">
                <seg.icon className="w-4.5 h-4.5 text-accent" strokeWidth={1.75} />
              </div>
              <h3 className="text-sm font-semibold text-text-primary mb-2">{seg.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">{seg.benefit}</p>
            </m.div>
          ))}
        </div>
      </div>
    </section>
  )
}
