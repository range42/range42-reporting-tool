import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'

export interface RouteFlags {
  requiresAuth?: boolean
  requiresAdmin?: boolean
  requiresApprover?: boolean
  loginPage?: boolean
  public?: boolean
}

const EXERCISE_PATH = /^\/exercises\/([^/]+)/

/** Return a redirect path, or null to allow navigation. Pure for testability. */
export function resolveNavigation(flags: RouteFlags, to: string): string | null {
  const auth = useAuthStore()
  if (flags.loginPage && auth.isAuthenticated) return '/exercises'
  if (flags.requiresAuth && !auth.isAuthenticated) return '/login'
  if (flags.requiresAdmin && !auth.isAdmin) return '/exercises'
  if (flags.requiresApprover && !auth.isAdmin) {
    // Coarse gate: global admins always pass; others need the cached reports:approve
    // capability for the exercise in the path (populated on entering the exercise).
    const exerciseId = EXERCISE_PATH.exec(to)?.[1]
    if (!exerciseId || !useCapabilitiesStore().canApproveReports(exerciseId)) return '/exercises'
  }
  return null
}
