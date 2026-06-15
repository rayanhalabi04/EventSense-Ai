import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { authService } from '../services/auth'
import { useAuthStore } from '../store/authStore'
import type { LoginRequest } from '../types'

export function useLogin() {
  const { setToken, setUser } = useAuthStore()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async (data: LoginRequest) => {
      const tokenRes = await authService.login(data)
      setToken(tokenRes.access_token)
      const user = authService.userFromToken(tokenRes.access_token, data.email)
      if (!user) {
        throw new Error('Login succeeded, but the access token could not be read.')
      }
      setUser(user)
      return user
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth'] })
      navigate('/overview')
    },
  })
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: authService.logout,
    onSettled: () => {
      logout()
      queryClient.clear()
      navigate('/login')
    },
  })
}
