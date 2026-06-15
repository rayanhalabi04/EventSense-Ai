import { api } from './api'
import type { LoginRequest, TokenResponse, User } from '../types'

type JwtPayload = {
  sub?: string
  tenant_id?: string
  role?: User['role']
  exp?: number
}

function decodeJwtPayload(token: string): JwtPayload | null {
  const payload = token.split('.')[1]
  if (!payload) return null

  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=')
    return JSON.parse(atob(padded)) as JwtPayload
  } catch {
    return null
  }
}

function displayNameFromEmail(email: string): string {
  const [name] = email.split('@')
  return name
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ') || email
}

export const authService = {
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    // Email + password only; the backend resolves the tenant from the email.
    const res = await api.post<TokenResponse>('/api/v1/auth/login', data)
    return res.data
  },

  userFromToken: (token: string, email = 'user@example.com'): User | null => {
    const payload = decodeJwtPayload(token)
    if (!payload?.sub || !payload.tenant_id || !payload.role) return null

    if (payload.exp && payload.exp * 1000 <= Date.now()) return null

    return {
      id: payload.sub,
      email,
      full_name: displayNameFromEmail(email),
      role: payload.role,
      tenant_id: payload.tenant_id,
      is_active: true,
    }
  },

  me: async (): Promise<User> => {
    const res = await api.get<User>('/auth/me')
    return res.data
  },

  logout: async (): Promise<void> => {
    await api.post('/auth/logout')
  },

  refresh: async (): Promise<TokenResponse> => {
    const res = await api.post<TokenResponse>('/auth/refresh')
    return res.data
  },
}
