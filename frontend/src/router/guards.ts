import { useAuthStore } from '@/stores/auth'

export interface RouteFlags {
  requiresAuth?: boolean
  requiresAdmin?: boolean
  loginPage?: boolean
  public?: boolean
}

/** Return a redirect path, or null to allow navigation. Pure for testability. */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function resolveNavigation(flags: RouteFlags, _to: string): string | null {
  const auth = useAuthStore()
  if (flags.loginPage && auth.isAuthenticated) return '/exercises'
  if (flags.requiresAuth && !auth.isAuthenticated) return '/login'
  if (flags.requiresAdmin && !auth.isAdmin) return '/exercises'
  return null
}
