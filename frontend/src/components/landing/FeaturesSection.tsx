import { m } from 'framer-motion'
import {
  MessageSquare,
  AlertTriangle,
  CheckSquare,
  Search,
  Sparkles,
  ArrowUpCircle,
} from 'lucide-react'

const features = [
  {
    icon: MessageSquare,
    title: 'Organized client conversations',
    description:
      'Every WhatsApp message, email thread, and inquiry lands in one structured inbox — sorted by status, risk, and urgency. No more scrolling through chats.',
  },
  {
    icon: AlertTriangle,
    title: 'Instant risk detection',
    description:
      'EventSense automatically flags cancellations, complaints, payment disputes, and sudden guest-count changes before they become operational crises.',
  },
  {
    icon: CheckSquare,
    title: 'Messages become tasks',
    description:
      'When a client requests something, a task is created automatically — assigned, prioritized, and tracked alongside the conversation that triggered it.',
  },
  {
    icon: Search,
    title: 'Internal document search',
    description:
      'AI-powered retrieval pulls answers from your contracts, pricing sheets, FAQs, and policies so your team can reply accurately and fast.',
  },
  {
    icon: Sparkles,
    title: 'Professional reply suggestions',
    description:
      'Grounded in your actual documents, EventSense drafts replies that sound like your team wrote them — not a generic chatbot.',
  },
  {
    icon: ArrowUpCircle,
    title: 'Manager escalation',
    description:
      'Urgent situations are flagged and routed to the right manager with full conversation context — no handoff confusion, no dropped balls.',
  },
]

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
}

const item = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
}

export function FeaturesSection() {
  return (
    <section id="features" className="py-24 bg-surface">
      <div className="max-w-6xl mx-auto px-6">
        <m.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <p className="section-label mb-4">What EventSense does</p>
          <h2 className="font-display text-4xl font-medium text-text-primary leading-tight max-w-2xl mx-auto">
            Operations intelligence for every part of your event workflow
          </h2>
        </m.div>

        <m.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid md:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          {features.map((feat) => (
            <m.div
              key={feat.title}
              variants={item}
              whileHover={{ y: -4, boxShadow: '0 12px 32px rgba(23,32,51,0.10)' }}
              className="bg-bg-warm rounded-lg p-6 border border-border transition-shadow"
            >
              <div className="w-10 h-10 rounded-lg bg-accent-soft border border-accent/20 flex items-center justify-center mb-4">
                <feat.icon className="w-5 h-5 text-accent" strokeWidth={1.75} />
              </div>
              <h3 className="text-base font-semibold text-text-primary mb-2">{feat.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">{feat.description}</p>
            </m.div>
          ))}
        </m.div>
      </div>
    </section>
  )
}
