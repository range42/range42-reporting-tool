import { apiGet, apiPost } from '@/services/http'

export interface AuthUser {
  id: string
  email: string
  display_name: string
  avatar_url: string | null
  is_global_admin: boolean
}
export interface Session {
  access_token: string
  token_type: string
  user: AuthUser
}

export const emergencyLogin = (password: string): Promise<Session> =>
  apiPost<Session>('/api/v1/auth/emergency-login', { password })

export const completeOidcCallback = (code: string, state: string): Promise<Session> =>
  apiGet<Session>(
    `/api/v1/auth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
  )

export const fetchMe = (token: string): Promise<AuthUser> =>
  apiGet<AuthUser>('/api/v1/auth/me', token)

export const refreshSession = (token: string): Promise<Session> =>
  apiPost<Session>('/api/v1/auth/refresh', undefined, token)

export const logoutSession = (token: string): Promise<{ revoked: boolean }> =>
  apiPost<{ revoked: boolean }>('/api/v1/auth/logout', undefined, token)
