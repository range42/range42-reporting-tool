<script setup lang="ts">
/**
 * Shared "pick a candidate, add, list current, remove" panel — the identical shape
 * `TeamEvaluators.vue` and `CampaignEvaluators.vue` each had duplicated. Extracted so
 * `CampaignDetail.vue` can mount one instance per team plus one for the campaign itself
 * without re-implementing the picker.
 *
 * Presentational + local `picked` state only: data loading, add/remove calls, and the
 * resulting list all stay owned by the caller (emits `assign`/`remove`, takes `rows` as a
 * prop) — this component never calls a service directly.
 *
 * `testPrefix` disambiguates `data-test` ids when more than one instance is mounted on one
 * page; left empty, ids match the original single-instance screens exactly (`assign-pick`,
 * not `assign-pick-`), so existing tests for those screens keep passing unchanged.
 */
import { computed, ref } from 'vue'
import { UserMinus, UserPlus } from '@lucide/vue'
import type { EvaluatorCandidate } from '@/services/evaluations'

interface Row {
  id: string
  evaluator_id: string
  display_name: string
  email: string
}

const props = withDefaults(
  defineProps<{
    rows: Row[]
    candidates: EvaluatorCandidate[]
    assigning?: boolean
    assignError?: string
    testPrefix?: string
    addHeading: string
    noCandidatesText: string
    pickLabel: string
    assignActionText: string
    currentHeading: string
    nobodyText: string
    removeActionText: string
  }>(),
  { assigning: false, assignError: '', testPrefix: '' },
)

const emit = defineEmits<{ assign: [evaluatorId: string]; remove: [evaluatorId: string] }>()

const picked = ref('')

const offerable = computed(() =>
  props.candidates.filter((c) => !props.rows.some((r) => r.evaluator_id === c.user_id)),
)

function testId(name: string): string {
  return props.testPrefix ? `${name}-${props.testPrefix}` : name
}

function onAssign(): void {
  if (picked.value === '' || props.assigning) return
  emit('assign', picked.value)
  picked.value = ''
}
</script>

<template>
  <div>
    <section class="mb-8 space-y-2">
      <h2 class="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {{ addHeading }}
      </h2>

      <p
        v-if="candidates.length === 0"
        :data-test="testId('assign-no-candidates')"
        class="text-sm text-zinc-500"
      >
        {{ noCandidatesText }}
      </p>

      <div v-else class="flex flex-wrap items-center gap-2">
        <label :for="testId('evaluator-pick')" class="sr-only">{{ pickLabel }}</label>
        <select
          :id="testId('evaluator-pick')"
          v-model="picked"
          :data-test="testId('assign-pick')"
          class="h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">{{ pickLabel }}</option>
          <option v-for="c in offerable" :key="c.user_id" :value="c.user_id">
            {{ c.display_name }} ({{ c.email }})
          </option>
        </select>
        <button
          type="button"
          :data-test="testId('assign-submit')"
          :disabled="picked === '' || assigning"
          class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
          @click="onAssign"
        >
          <UserPlus class="h-4 w-4" />
          {{ assignActionText }}
        </button>
      </div>

      <p v-if="assignError" :data-test="testId('assign-error')" class="text-sm text-red-500">
        {{ assignError }}
      </p>
    </section>

    <section class="space-y-2">
      <h2 class="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {{ currentHeading }}
      </h2>

      <p v-if="rows.length === 0" :data-test="testId('assign-none')" class="text-sm text-zinc-500">
        {{ nobodyText }}
      </p>

      <ul v-else class="space-y-1.5">
        <li
          v-for="r in rows"
          :key="r.id"
          :data-test="`assign-row-${r.id}`"
          class="flex items-center justify-between rounded-lg border border-zinc-200 px-3.5 py-2.5 dark:border-zinc-800"
        >
          <span class="text-sm"
            >{{ r.display_name }} <span class="text-zinc-500">({{ r.email }})</span></span
          >
          <button
            type="button"
            :data-test="`assign-remove-${r.id}`"
            class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-red-500 transition hover:bg-red-500/10"
            @click="emit('remove', r.evaluator_id)"
          >
            <UserMinus class="h-3.5 w-3.5" />
            {{ removeActionText }}
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
