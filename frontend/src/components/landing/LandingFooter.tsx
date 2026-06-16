import { Link } from 'react-router-dom'
import { Logo } from '../Logo'

// Computed once at module load (not during render) so the value is stable
// for the session and never produces a server/client hydration mismatch.
const CURRENT_YEAR = new Date().getFullYear()

export function LandingFooter() {
  return (
    <footer className="bg-bg-warm border-t border-border py-12">
      <div className="max-w-6xl mx-auto px-6">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <Logo variant="light" className="w-11 h-11" />
              <span className="text-sm font-semibold text-text-primary">EventSense</span>
            </div>
            <p className="text-xs text-text-muted max-w-xs">
              Intelligent operations platform for professional event and wedding teams.
            </p>
          </div>

          {/* Links */}
          <nav className="flex flex-wrap gap-x-8 gap-y-2">
            <a href="#features" className="text-sm text-text-muted hover:text-text-primary transition-colors">Features</a>
            <a href="#how-it-works" className="text-sm text-text-muted hover:text-text-primary transition-colors">How it works</a>
            <a href="#testimonials" className="text-sm text-text-muted hover:text-text-primary transition-colors">Testimonials</a>
            <Link to="/login" className="text-sm text-text-muted hover:text-text-primary transition-colors">Sign in</Link>
          </nav>
        </div>

        <div className="mt-8 pt-6 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-text-muted">
            &copy; {CURRENT_YEAR} EventSense. All rights reserved.
          </p>
          <p className="text-xs text-text-muted">
            Built for professional event operations.
          </p>
        </div>
      </div>
    </footer>
  )
}
