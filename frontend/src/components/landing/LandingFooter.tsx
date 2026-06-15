import { Link } from 'react-router-dom'

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
              <div className="w-7 h-7 rounded-md bg-primary flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                  <rect x="2" y="1" width="12" height="14" rx="2" stroke="#C8A96A" strokeWidth="1.2"/>
                  <line x1="4.5" y1="5" x2="11.5" y2="5" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
                  <line x1="4.5" y1="8" x2="9.5" y2="8" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
                  <line x1="4.5" y1="11" x2="8" y2="11" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
              </div>
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
