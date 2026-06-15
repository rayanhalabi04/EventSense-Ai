import { useState } from 'react'
import { Link } from 'react-router-dom'
import { m } from 'framer-motion'
import { Eye, EyeOff, AlertCircle } from 'lucide-react'
import { useLogin } from '../hooks/useAuth'

export function LoginPage() {
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const login = useLogin()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    login.mutate(form)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  return (
    <div className="min-h-screen bg-bg-warm flex">
      {/* Left: Decorative panel */}
      <div className="hidden lg:flex lg:w-[480px] bg-primary flex-col justify-between p-12 relative overflow-hidden flex-shrink-0">
        {/* Background decoration */}
        <div className="absolute inset-0">
          <div className="absolute top-0 right-0 w-96 h-96 rounded-full bg-accent/6 blur-3xl" />
          <div className="absolute bottom-0 left-0 w-64 h-64 rounded-full bg-white/3 blur-3xl" />
          <svg className="absolute inset-0 w-full h-full opacity-[0.04]" aria-hidden>
            <defs>
              <pattern id="lgrid" width="48" height="48" patternUnits="userSpaceOnUse">
                <path d="M 48 0 L 0 0 0 48" fill="none" stroke="#FFFFFF" strokeWidth="1"/>
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#lgrid)" />
          </svg>
        </div>

        {/* Logo */}
        <div className="relative flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-accent flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="1" width="12" height="14" rx="2" stroke="#172033" strokeWidth="1.2"/>
              <line x1="4.5" y1="5" x2="11.5" y2="5" stroke="#172033" strokeWidth="1.2" strokeLinecap="round"/>
              <line x1="4.5" y1="8" x2="9.5" y2="8" stroke="#172033" strokeWidth="1.2" strokeLinecap="round"/>
              <line x1="4.5" y1="11" x2="8" y2="11" stroke="#172033" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-white leading-none">EventSense</p>
            <p className="text-[10px] text-white/40 mt-0.5 font-medium tracking-wider uppercase">Operations</p>
          </div>
        </div>

        {/* Tagline */}
        <div className="relative">
          <p className="font-display text-3xl font-medium text-white leading-snug mb-4">
            Every message, every task, every client — under control.
          </p>
          <p className="text-sm text-white/50 leading-relaxed">
            Sign in to access your event operations dashboard.
          </p>
        </div>

        {/* Trust indicators */}
        <div className="relative space-y-3">
          {[
            'Organized client inbox with risk detection',
            'AI-suggested replies from your documents',
            'Tasks, escalations, and audit trails',
          ].map((item) => (
            <div key={item} className="flex items-center gap-2.5">
              <div className="w-4 h-4 rounded-full bg-accent/20 border border-accent/30 flex items-center justify-center flex-shrink-0">
                <div className="w-1.5 h-1.5 rounded-full bg-accent" />
              </div>
              <p className="text-xs text-white/60">{item}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Right: Login form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <m.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-md"
        >
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <rect x="2" y="1" width="12" height="14" rx="2" stroke="#C8A96A" strokeWidth="1.2"/>
                <line x1="4.5" y1="5" x2="11.5" y2="5" stroke="#C8A96A" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
            </div>
            <span className="text-sm font-semibold text-text-primary">EventSense</span>
          </div>

          <h1 className="font-display text-3xl font-medium text-text-primary mb-1.5">Sign in</h1>
          <p className="text-sm text-text-muted mb-8">
            Access your operations dashboard.{' '}
            <Link to="/" className="text-accent hover:underline">Back to home</Link>
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-text-primary mb-1.5">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                autoComplete="email"
                placeholder="you@yourcompany.com"
                value={form.email}
                onChange={handleChange}
                className="input-base"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-text-primary mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={handleChange}
                  className="input-base pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((p) => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {login.isError && (
              <m.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 p-3 bg-danger-soft border border-danger/20 rounded-md"
              >
                <AlertCircle className="w-4 h-4 text-danger flex-shrink-0" />
                <p className="text-xs text-danger">
                  {(login.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Invalid credentials. Please check your email and password.'}
                </p>
              </m.div>
            )}

            <button
              type="submit"
              disabled={login.isPending}
              className="btn-primary w-full py-2.5 mt-2 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {login.isPending ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </m.div>
      </div>
    </div>
  )
}
