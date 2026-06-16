import { useState, useEffect, useCallback } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { ChevronLeft, ChevronRight, MessageSquare, AlertTriangle, CheckSquare, ArrowUpCircle, LayoutDashboard } from 'lucide-react'

const useCases = [
  {
    icon: MessageSquare,
    tag: 'Inbox Management',
    title: 'Managing hundreds of WhatsApp conversations without losing track',
    description:
      'Wedding planners and event agencies handle dozens of simultaneous client threads. EventSense centralizes every conversation, flags priority issues at the top, and keeps your team aligned on what needs a response.',
    stats: [
      { value: '47', label: 'open threads today' },
      { value: '3', label: 'urgent responses needed' },
      { value: '94%', label: 'same-day response rate' },
    ],
    accentColor: '#3B6F8F',
    accentBg: '#E6F1F6',
  },
  {
    icon: AlertTriangle,
    tag: 'Risk Detection',
    title: 'Catching client cancellations and complaints before they escalate',
    description:
      'A message that starts with "We need to talk about the guest list" could mean anything. EventSense automatically classifies intent and risk level — so your team sees threats and acts fast.',
    stats: [
      { value: '98%', label: 'intent detection accuracy' },
      { value: '< 2s', label: 'classification time' },
      { value: '12', label: 'risk signals tracked' },
    ],
    accentColor: '#A33A3A',
    accentBg: '#FBE6E6',
  },
  {
    icon: CheckSquare,
    tag: 'Task Automation',
    title: 'Turning every client request into a tracked, assigned task',
    description:
      'When a bride asks about seating arrangements or a corporate client requests revised catering numbers, EventSense creates a task, links it to the conversation, and tracks it to completion.',
    stats: [
      { value: '156', label: 'tasks created this week' },
      { value: '89%', label: 'resolved before deadline' },
      { value: '0', label: 'requests dropped' },
    ],
    accentColor: '#2F7D5B',
    accentBg: '#E4F3EC',
  },
  {
    icon: ArrowUpCircle,
    tag: 'Manager Escalation',
    title: 'Routing critical situations to managers with full context',
    description:
      'A venue change request three days before an event. A client threatening to cancel. EventSense escalates these to the right manager instantly — with the full conversation thread attached.',
    stats: [
      { value: '8', label: 'escalations this month' },
      { value: '100%', label: 'manager acknowledgement rate' },
      { value: '4h', label: 'avg resolution time' },
    ],
    accentColor: '#B7791F',
    accentBg: '#FFF4D8',
  },
  {
    icon: LayoutDashboard,
    tag: 'Operations Overview',
    title: 'One dashboard for your entire event operations pipeline',
    description:
      'From the overview screen, your team sees open conversations, pending tasks, active escalations, and risk trends across every client and every event — always current, always calm.',
    stats: [
      { value: '12', label: 'events in active planning' },
      { value: '34', label: 'tasks across all clients' },
      { value: '2', label: 'escalations open' },
    ],
    accentColor: '#172033',
    accentBg: '#F3E8D2',
  },
]

export function UseCaseCarousel() {
  const [current, setCurrent] = useState(0)
  const [direction, setDirection] = useState<1 | -1>(1)

  const prev = useCallback(() => {
    setDirection(-1)
    setCurrent((c) => (c - 1 + useCases.length) % useCases.length)
  }, [])

  const next = useCallback(() => {
    setDirection(1)
    setCurrent((c) => (c + 1) % useCases.length)
  }, [])

  // Auto-advance every 5s
  useEffect(() => {
    const id = setInterval(next, 5000)
    return () => clearInterval(id)
  }, [next])

  const slide = useCases[current]
  const Icon = slide.icon

  const variants = {
    enter: (d: number) => ({ opacity: 0, x: d * 60 }),
    center: { opacity: 1, x: 0 },
    exit: (d: number) => ({ opacity: 0, x: d * -60 }),
  }

  return (
    <section className="py-24 bg-bg-warm overflow-hidden">
      <div className="max-w-6xl mx-auto px-6">
        <m.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-14"
        >
          <p className="section-label mb-4">Real-world scenarios</p>
          <h2 className="font-display text-4xl font-medium text-text-primary leading-tight">
            What EventSense looks like in practice
          </h2>
        </m.div>

        <div className="relative">
          <div className="overflow-hidden rounded-xl border border-border shadow-card bg-surface">
            <AnimatePresence custom={direction} mode="wait">
              <m.div
                key={current}
                custom={direction}
                variants={variants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.35, ease: [0.32, 0, 0.67, 0] }}
                className="grid lg:grid-cols-2"
              >
                {/* Left: Content */}
                <div className="p-8 lg:p-12 flex flex-col justify-between">
                  <div>
                    <div
                      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold mb-5"
                      style={{ background: slide.accentBg, color: slide.accentColor }}
                    >
                      <Icon className="w-3.5 h-3.5" strokeWidth={2} />
                      {slide.tag}
                    </div>
                    <h3 className="font-display text-2xl lg:text-3xl font-medium text-text-primary leading-snug mb-4">
                      {slide.title}
                    </h3>
                    <p className="text-base text-text-muted leading-relaxed">
                      {slide.description}
                    </p>
                  </div>

                  <div className="mt-8 grid grid-cols-3 gap-4">
                    {slide.stats.map((stat) => (
                      <div key={stat.label}>
                        <p className="text-2xl font-semibold text-text-primary" style={{ color: slide.accentColor }}>
                          {stat.value}
                        </p>
                        <p className="text-xs text-text-muted mt-0.5">{stat.label}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Right: Visual card */}
                <div
                  className="p-8 lg:p-12 flex items-center justify-center min-h-[280px]"
                  style={{ background: slide.accentBg }}
                >
                  <div className="w-full max-w-[280px] bg-surface rounded-xl border border-border shadow-card p-5">
                    <div className="flex items-center gap-2.5 mb-4">
                      <div
                        className="w-9 h-9 rounded-lg flex items-center justify-center"
                        style={{ background: slide.accentColor + '18' }}
                      >
                        <Icon className="w-4.5 h-4.5" style={{ color: slide.accentColor }} strokeWidth={1.75} />
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-text-primary">{slide.tag}</p>
                        <p className="text-[10px] text-text-muted">EventSense AI</p>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {slide.stats.map((stat) => (
                        <div key={stat.label} className="flex items-center justify-between py-1.5 border-b border-border last:border-0">
                          <span className="text-xs text-text-muted">{stat.label}</span>
                          <span className="text-sm font-semibold" style={{ color: slide.accentColor }}>
                            {stat.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </m.div>
            </AnimatePresence>
          </div>

          {/* Navigation controls */}
          <div className="flex items-center justify-between mt-6">
            <div className="flex gap-2">
              {useCases.map((uc, i) => (
                <button
                  key={uc.tag}
                  type="button"
                  onClick={() => { setDirection(i > current ? 1 : -1); setCurrent(i) }}
                  aria-label={`Go to slide ${i + 1}: ${uc.tag}`}
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    i === current ? 'w-8 bg-primary' : 'w-1.5 bg-border-strong'
                  }`}
                />
              ))}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={prev}
                aria-label="Previous slide"
                className="w-9 h-9 rounded-lg border border-border bg-surface hover:bg-surface-warm flex items-center justify-center transition-colors"
              >
                <ChevronLeft className="w-4 h-4 text-text-muted" />
              </button>
              <button
                type="button"
                onClick={next}
                aria-label="Next slide"
                className="w-9 h-9 rounded-lg border border-border bg-surface hover:bg-surface-warm flex items-center justify-center transition-colors"
              >
                <ChevronRight className="w-4 h-4 text-text-muted" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
