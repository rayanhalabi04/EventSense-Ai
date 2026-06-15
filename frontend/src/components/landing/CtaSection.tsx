import { Link } from 'react-router-dom'
import { m } from 'framer-motion'
import { ArrowRight } from 'lucide-react'

export function CtaSection() {
  return (
    <section className="py-24 bg-primary relative overflow-hidden">
      {/* Decorative glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] rounded-full bg-accent/10 blur-3xl" />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-accent/5 blur-3xl" />
        {/* Grid */}
        <svg className="absolute inset-0 w-full h-full opacity-[0.04]" aria-hidden>
          <defs>
            <pattern id="grid-dark" width="64" height="64" patternUnits="userSpaceOnUse">
              <path d="M 64 0 L 0 0 0 64" fill="none" stroke="#FFFFFF" strokeWidth="1"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid-dark)" />
        </svg>
      </div>

      <div className="relative max-w-4xl mx-auto px-6 text-center">
        <m.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent/15 border border-accent/25 rounded-full mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-accent" />
            <span className="text-xs font-medium text-accent">Start in minutes</span>
          </div>

          <h2 className="font-display text-5xl font-medium text-white leading-tight mb-5">
            Ready to bring calm<br />to your event operations?
          </h2>

          <p className="text-base text-white/60 leading-relaxed max-w-lg mx-auto mb-10">
            EventSense is built for teams who are serious about client experience and operational clarity. Get started and see it working on your own conversations.
          </p>

          <div className="flex flex-wrap gap-3 justify-center">
            <Link to="/login" className="inline-flex items-center gap-2 px-7 py-3.5 bg-accent text-primary font-semibold text-sm rounded-md hover:bg-accent/90 transition-all active:scale-[0.98]">
              Get started now
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a
              href="#features"
              className="inline-flex items-center gap-2 px-7 py-3.5 bg-white/8 text-white font-semibold text-sm rounded-md border border-white/15 hover:bg-white/12 transition-all active:scale-[0.98]"
            >
              Learn more about EventSense features
            </a>
          </div>
        </m.div>
      </div>
    </section>
  )
}
