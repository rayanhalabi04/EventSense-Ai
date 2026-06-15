import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

interface Props {
  children: React.ReactNode
  requiredRole?: 'staff' | 'manager' | 'platform_admin'
}

const ROLE_WEIGHT: Record<string, number> = {
  staff: 1,
  manager: 2,
  platform_admin: 3,
}

export function ProtectedRoute({ children, requiredRole }: Props) {
  const { token, user } = useAuthStore()
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requiredRole && user) {
    const userWeight = ROLE_WEIGHT[user.role] ?? 0
    const requiredWeight = ROLE_WEIGHT[requiredRole] ?? 0
    if (userWeight < requiredWeight) {
      return <Navigate to="/" replace />
    }
  }

  return <>{children}</>
}
