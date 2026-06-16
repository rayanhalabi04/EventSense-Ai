import { m } from 'framer-motion'
import { MessageSquare, Cpu, ClipboardList, Send } from 'lucide-react'

const steps = [
  {
    number: '01',
    icon: MessageSquare,
    title: 'Client sends a message',
    description:
      'Your client sends a WhatsApp message, email, or any other channel message. It arrives in your EventSense inbox instantly.',
  },
  {
    number: '02',
    icon: Cpu,
    title: 'AI classifies and assesses risk',
    description:
      'EventSense reads the message, identifies the intent — cancellation, complaint, inquiry, confirmation — and assigns a risk level in seconds.',
  },
  {
    number: '03',
    icon: ClipboardList,
    title: 'Tasks and escalations are created',
    description:
      'Action items are extracted automatically. Urgent cases are escalated to managers. Everything is tracked, prioritized, and linked to the original conversation.',
  },
  {
    number: '04',
    icon: Send,
    title: 'Your team responds professionally',
    description:
      'EventSense drafts a reply grounded in your own documents. Your team reviews, edits if needed, and sends — confident the response is accurate and on-brand.',
  },
]

export function HowItWorksSection() {
  return (
    <section id="how-it-works" className="py-24 bg-surface">
      <div className="max-w-6xl mx-auto px-6">
        <m.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <p className="section-label mb-4">How it works</p>
          <h2 className="font-display text-4xl font-medium text-text-primary leading-tight max-w-xl mx-auto">
            From message received to action taken
          </h2>
        </m.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 relative">
          {/* Connecting line (desktop) */}
          <div className="hidden lg:block absolute top-10 left-[12.5%] right-[12.5%] h-px bg-gradient-to-r from-transparent via-border to-transparent" />

          {steps.map((step, i) => (
            <m.div
              key={step.number}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              className="relative flex flex-col items-center text-center"
            >
              {/* Step number + icon */}
              <div className="relative mb-5">
                <div className="w-16 h-16 rounded-full bg-bg-warm border-2 border-border flex items-center justify-center">
                  <step.icon className="w-6 h-6 text-primary" strokeWidth={1.75} />
                </div>
                <div className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-accent text-primary text-[10px] font-bold flex items-center justify-center">
                  {step.number.slice(-1)}
                </div>
              </div>
              <h3 className="text-sm font-semibold text-text-primary mb-2">{step.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">{step.description}</p>
            </m.div>
          ))}
        </div>
      </div>
    </section>
  )
}
