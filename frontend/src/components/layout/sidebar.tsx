import { NavLink, useNavigate } from 'react-router-dom'
import { m } from 'framer-motion'
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  CheckSquare,
  AlertTriangle,
  ClipboardList,
  FlaskConical,
  LogOut,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useLogout } from '../../hooks/useAuth'

const navItems = [
  { to: '/overview', icon: LayoutDashboard, label: 'Overview', exact: true },
  { to: '/inbox', icon: MessageSquare, label: 'Inbox' },
  { to: '/tasks', icon: CheckSquare, label: 'Tasks' },
  { to: '/escalations', icon: AlertTriangle, label: 'Escalations' },
  { to: '/documents', icon: FileText, label: 'Documents' },
  { to: '/audit-logs', icon: ClipboardList, label: 'Audit Logs', managerOnly: true },
  { to: '/evaluation', icon: FlaskConical, label: 'Evaluation' },
]

export function Sidebar() {
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout.mutate()
    navigate('/login')
  }

  const isManager = user?.role === 'manager' || user?.role === 'platform_admin'

  const initials = user?.full_name
    ? user.full_name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()
    : '?'

  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-primary flex flex-col z-40 select-none">
      {/* Logo */}
      <div className="px-5 pt-6 pb-5 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
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
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        <div className="space-y-0.5">
          {navItems.map((item) => {
            if (item.managerOnly && !isManager) return null
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.exact}
                className={({ isActive }) =>
                  `group flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-all duration-150 ${
                    isActive
                      ? 'bg-white/10 text-white'
                      : 'text-white/55 hover:bg-white/6 hover:text-white/80'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="flex items-center gap-2.5">
                      <item.icon className={`w-4 h-4 flex-shrink-0 transition-colors ${isActive ? 'text-accent' : 'text-white/40 group-hover:text-white/60'}`} />
                      {item.label}
                    </span>
                    {isActive && (
                      <m.span
                        layoutId="nav-indicator"
                        className="w-1.5 h-1.5 rounded-full bg-accent"
                      />
                    )}
                  </>
                )}
              </NavLink>
            )
          })}
        </div>
      </nav>

      {/* User footer */}
      <div className="px-3 pb-4 border-t border-white/10 pt-3">
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-md mb-1">
          <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/30 flex items-center justify-center flex-shrink-0">
            <span className="text-[10px] font-semibold text-accent">{initials}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-white truncate">{user?.full_name ?? 'User'}</p>
            <p className="text-[10px] text-white/40 capitalize">{user?.role?.replace('_', ' ')}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-white/40 hover:text-white/70 hover:bg-white/6 rounded-md transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
