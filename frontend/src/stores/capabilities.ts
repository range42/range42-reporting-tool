import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMyCapabilities } from '@/services/exercises'

const REPORTS_APPROVE = 'reports:approve'

/**
 * Per-exercise capability cache. Populated from `GET /exercises/{id}/me` and read
 * synchronously by the `requiresApprover` route guard and approver-gated nav.
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

  /** Fetch and cache the caller's capabilities for an exercise (idempotent to re-call). */
  async function load(token: string, exerciseId: string): Promise<void> {
    set(exerciseId, (await getMyCapabilities(token, exerciseId)).capabilities)
  }

  return { byExercise, set, has, canApproveReports, load }
})
