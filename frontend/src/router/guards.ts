import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'

export interface RouteFlags {
  requiresAuth?: boolean
  requiresAdmin?: boolean
  requiresApprover?: boolean
  requiresEvaluator?: boolean
  loginPage?: boolean
  public?: boolean
}

const EXERCISE_PATH = /^\/exercises\/([^/]+)/

/** Whether the cached capabilities for the exercise in `path` carry the given grant.
 *  A path with no exercise segment can never satisfy an exercise-scoped capability. */
function hasExerciseCapability(path: string, grant: 'approve' | 'evaluate'): boolean {
  const exerciseId = EXERCISE_PATH.exec(path)?.[1]
  if (!exerciseId) return false
  const capabilities = useCapabilitiesStore()
  return grant === 'approve'
    ? capabilities.canApproveReports(exerciseId)
    : capabilities.canEvaluate(exerciseId)
}

/** Return a redirect path, or null to allow navigation. Pure for testability. */
export function resolveNavigation(flags: RouteFlags, to: string): string | null {
  const auth = useAuthStore()
  if (flags.loginPage && auth.isAuthenticated) return '/exercises'
  if (flags.requiresAuth && !auth.isAuthenticated) return '/login'
  if (flags.requiresAdmin && !auth.isAdmin) return '/exercises'
  // Coarse capability gates: global admins always pass; everyone else needs the cached
  // capability for the exercise in the path (populated on entering the exercise). Neither
  // gate decides WHICH report the caller may touch — that is the server's D1 (E1) scoping.
  if (flags.requiresApprover && !auth.isAdmin && !hasExerciseCapability(to, 'approve'))
    return '/exercises'
  if (flags.requiresEvaluator && !auth.isAdmin && !hasExerciseCapability(to, 'evaluate'))
    return '/exercises'
  return null
}
