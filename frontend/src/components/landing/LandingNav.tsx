import { Link } from 'react-router-dom'
import { m } from 'framer-motion'

export function LandingNav() {
  return (
    <m.header
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-4 bg-bg-warm/90 backdrop-blur-md border-b border-border/40"
    >
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="1" width="12" height="14" rx="2" stroke="#C8A96A" strokeWidth="1.2"/>
            <line x1="4.5" y1="5" x2="11.5" y2="5" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="4.5" y1="8" x2="9.5" y2="8" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="4.5" y1="11" x2="8" y2="11" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="text-sm font-semibold text-text-primary tracking-tight">EventSense</span>
      </div>

      <nav className="hidden md:flex items-center gap-6">
        <a href="#features" className="text-sm text-text-muted hover:text-text-primary transition-colors">Features</a>
        <a href="#how-it-works" className="text-sm text-text-muted hover:text-text-primary transition-colors">How it works</a>
        <a href="#testimonials" className="text-sm text-text-muted hover:text-text-primary transition-colors">Testimonials</a>
      </nav>

      <div className="flex items-center gap-3">
        <Link to="/login" className="text-sm font-medium text-text-muted hover:text-text-primary transition-colors">
          Sign in
        </Link>
        <Link to="/login" className="btn-primary text-sm py-2 px-4">
          Get started
        </Link>
      </div>
    </m.header>
  )
}
