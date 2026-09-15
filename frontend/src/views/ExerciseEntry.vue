<script setup lang="ts">
/**
 * Neutral landing for an exercise: works out where the caller belongs, then replaces itself.
 *
 * Evaluators are exercise direction, not players. They go straight to their own queue and never
 * touch the team report list, which their role is refused by design. The decision keys on the
 * `evaluations:write` capability and deliberately NOT on `auth.isAdmin`: a global admin carries
 * every capability, so admins would otherwise be diverted out of the report list they run.
 *
 * Capabilities are loaded HERE because the decision needs them one step earlier than the report
 * list, which used to be the only place that fetched them.
 */
import { onMounted } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { Activity } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const caps = useCapabilitiesStore()

onMounted(async () => {
  const exerciseId = String(route.params.exerciseId)
  if (auth.token) {
    // A capability load that fails must not strand the caller on a blank page: fall through to
    // the report list, which surfaces its own error when the role may not read it.
    await caps.load(auth.token, exerciseId).catch(() => undefined)
  }
  const target: RouteLocationRaw =
    !auth.isAdmin && caps.canEvaluate(exerciseId)
      ? { name: 'evaluation-queue', params: { exerciseId } }
      : `/exercises/${exerciseId}/reports`
  await router.replace(target)
})
</script>

<template>
  <div data-test="exercise-entry" class="flex justify-center py-16 text-zinc-500">
    <Activity class="h-5 w-5 animate-spin" />
  </div>
</template>
