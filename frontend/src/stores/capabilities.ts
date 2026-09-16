import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMyCapabilities } from '@/services/exercises'

const REPORTS_APPROVE = 'reports:approve'
export const EVALUATIONS_WRITE = 'evaluations:write'

/**
 * Per-exercise capability cache. Populated from `GET /exercises/{id}/me` and read
 * synchronously by the `requiresApprover` / `requiresEvaluator` route guards and by
 * capability-gated nav.
 */
export const useCapabilitiesStore = defineStore('capabilities', () => {
  const byExercise = ref<Record<string, string[]>>({})

  function set(exerciseId: string, capabilities: string[]): void {
    byExercise.value = { ...byExercise.value, [exerciseId]: capabilities }
  }

  function has(exerciseId: string, capability: string): boolean {
    return (byExercise.value[exerciseId] ?? []).includes(capability)
  }

  const canApproveReports = (exerciseId: string): boolean => has(exerciseId, REPORTS_APPROVE)

  /** Coarse gate only: this says the caller grades SOMETHING in the exercise, never that
   *  they may grade a particular report — that scoping is the server's call. */
  const canEvaluate = (exerciseId: string): boolean => has(exerciseId, EVALUATIONS_WRITE)

  /** Fetch and cache the caller's capabilities for an exercise (idempotent to re-call). */
  async function load(token: string, exerciseId: string): Promise<void> {
    set(exerciseId, (await getMyCapabilities(token, exerciseId)).capabilities)
  }

  return { byExercise, set, has, canApproveReports, canEvaluate, load }
})
