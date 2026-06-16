import { Link } from 'react-router-dom'
import { m } from 'framer-motion'
import { Logo } from '../Logo'

export function LandingNav() {
  return (
    <m.header
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-4 bg-bg-warm/90 backdrop-blur-md border-b border-border/40"
    >
      <div className="flex items-center gap-2.5">
        <Logo variant="light" className="w-12 h-12" />
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
