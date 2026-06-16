import { m } from 'framer-motion'
import { Quote } from 'lucide-react'

const testimonials = [
  {
    quote:
      'Before EventSense, I was managing 30 active weddings out of a WhatsApp group and a spreadsheet. Now I can actually see which clients need urgent attention without reading every message.',
    name: 'Camille Beaumont',
    role: 'Principal Planner',
    company: 'Beaumont Bridal Studio',
    initials: 'CB',
  },
  {
    quote:
      'The risk detection alone has saved us from two near-disasters this season. When a client messaged about cancelling two weeks before their gala, we caught it within minutes and got on a call before it escalated.',
    name: 'James Okafor',
    role: 'Operations Director',
    company: 'Pinnacle Events Group',
    initials: 'JO',
  },
  {
    quote:
      'Our venue handles 14 events per month. The old way — text chains, shared inboxes, sticky notes — was holding us back. EventSense gives every coordinator the same real-time view of what\'s open.',
    name: 'Priya Nair',
    role: 'Venue Operations Manager',
    company: 'The Meridian Estate',
    initials: 'PN',
  },
  {
    quote:
      'I was skeptical about AI for client communication. But the suggested replies are actually good — they sound like us, reference our packages correctly, and save 40 minutes a day in drafting time.',
    name: 'Lucas Ferreira',
    role: 'Creative Director',
    company: 'Casa Flor Events',
    initials: 'LF',
  },
  {
    quote:
      'Managing dietary requests and last-minute headcount changes used to be a full-time job. Now those come in, tasks are created automatically, and my kitchen team gets notified before I even see the message.',
    name: 'Amara Svensson',
    role: 'Catering Operations Manager',
    company: 'Nordic Table Catering',
    initials: 'AS',
  },
  {
    quote:
      'I use the audit log to review every escalation each Friday. It\'s changed how we do post-event retrospectives — we have a clear record of what happened, when, and who acted on it.',
    name: 'David Chen',
    role: 'Agency Principal',
    company: 'Chen & Associates Events',
    initials: 'DC',
  },
]

export function TestimonialsSection() {
  return (
    <section id="testimonials" className="py-24 bg-surface">
      <div className="max-w-6xl mx-auto px-6">
        <m.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <p className="section-label mb-4">What teams say</p>
          <h2 className="font-display text-4xl font-medium text-text-primary leading-tight">
            Trusted by event professionals
          </h2>
        </m.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {testimonials.map((t, i) => (
            <m.div
              key={t.name}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, delay: i * 0.07 }}
              whileHover={{ y: -4 }}
              className="bg-bg-warm rounded-lg border border-border p-6 flex flex-col shadow-sm hover:shadow-card transition-all"
            >
              <Quote className="w-5 h-5 text-accent/60 mb-4 flex-shrink-0" strokeWidth={1.5} />
              <p className="text-sm text-text-body leading-relaxed flex-1 mb-5">
                &ldquo;{t.quote}&rdquo;
              </p>
              <div className="flex items-center gap-3 pt-4 border-t border-border">
                <div className="w-9 h-9 rounded-full bg-primary/8 border border-border flex items-center justify-center flex-shrink-0">
                  <span className="text-[10px] font-semibold text-text-primary">{t.initials}</span>
                </div>
                <div>
                  <p className="text-xs font-semibold text-text-primary">{t.name}</p>
                  <p className="text-[10px] text-text-muted">{t.role} &middot; {t.company}</p>
                </div>
              </div>
            </m.div>
          ))}
        </div>
      </div>
    </section>
  )
}
