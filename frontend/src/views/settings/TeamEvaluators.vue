<script setup lang="ts">
/**
 * Global-Admin assignment screen: which evaluator(s) watch this team.
 *
 * Independent of any campaign — see CampaignEvaluators.vue for the other half. A report only
 * auto-assigns an evaluator once both halves match for its team and campaign
 * (backend: reports.py::_auto_assign_evaluators).
 *
 * Unlike the per-report evaluator screen, removal here is a real delete: there is no grading
 * history tied to a team assignment to preserve.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UserMinus, UserPlus } from '@lucide/vue'
import AppShell from '@/components/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import { listEvaluatorCandidates, type EvaluatorCandidate } from '@/services/evaluations'
import {
  addTeamEvaluator,
  listTeamEvaluators,
  removeTeamEvaluator,
  type TeamEvaluatorSummary,
} from '@/services/teams'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const teamId = String(route.params.teamId)
const token = computed(() => auth.token ?? '')

const rows = ref<TeamEvaluatorSummary[]>([])
const candidates = ref<EvaluatorCandidate[]>([])
const picked = ref('')
const loading = ref(true)
const error = ref('')
const assignError = ref('')
const assigning = ref(false)

const offerable = computed(() =>
  candidates.value.filter((c) => !rows.value.some((r) => r.evaluator_id === c.user_id)),
)

async function load(): Promise<void> {
  rows.value = await listTeamEvaluators(token.value, exerciseId, teamId)
}

async function assign(): Promise<void> {
  if (picked.value === '' || assigning.value) return
  assigning.value = true
  assignError.value = ''
  try {
    await addTeamEvaluator(token.value, exerciseId, teamId, picked.value)
    picked.value = ''
    await load()
  } catch (e) {
    assignError.value = e instanceof ApiError ? e.message : t('teamEvaluators.assignFailed')
  } finally {
    assigning.value = false
  }
}

async function remove(evaluatorId: string): Promise<void> {
  assignError.value = ''
  try {
    await removeTeamEvaluator(token.value, exerciseId, teamId, evaluatorId)
    await load()
  } catch (e) {
    assignError.value = e instanceof ApiError ? e.message : t('teamEvaluators.removeFailed')
  }
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    candidates.value = await listEvaluatorCandidates(token.value, exerciseId)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('teamEvaluators.loadError')
  }
  loading.value = false
})
</script>

<template>
  <AppShell :title="t('teamEvaluators.title')">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('teamEvaluators.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('teamEvaluators.subtitle') }}</p>
    </div>

    <p v-if="loading" data-test="assign-loading" class="text-sm text-zinc-500">
      {{ t('teamEvaluators.loading') }}
    </p>

    <p v-else-if="error" data-test="assign-load-error" class="text-sm text-red-500">{{ error }}</p>

    <template v-else>
      <section class="mb-8 space-y-2">
        <h2 class="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {{ t('teamEvaluators.addHeading') }}
        </h2>

        <p
          v-if="candidates.length === 0"
          data-test="assign-no-candidates"
          class="text-sm text-zinc-500"
        >
          {{ t('teamEvaluators.noCandidates') }}
        </p>

        <div v-else class="flex flex-wrap items-center gap-2">
          <label for="team-evaluator-pick" class="sr-only">{{
            t('teamEvaluators.pickLabel')
          }}</label>
          <select
            id="team-evaluator-pick"
            v-model="picked"
            data-test="assign-pick"
            class="h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">{{ t('teamEvaluators.pickLabel') }}</option>
            <option v-for="c in offerable" :key="c.user_id" :value="c.user_id">
              {{ c.display_name }} ({{ c.email }})
            </option>
          </select>
          <button
            type="button"
            data-test="assign-submit"
            :disabled="picked === '' || assigning"
            class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
            @click="assign"
          >
            <UserPlus class="h-4 w-4" />
            {{ t('teamEvaluators.assignAction') }}
          </button>
        </div>

        <p v-if="assignError" data-test="assign-error" class="text-sm text-red-500">
          {{ assignError }}
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {{ t('teamEvaluators.currentHeading') }}
        </h2>

        <p v-if="rows.length === 0" data-test="assign-none" class="text-sm text-zinc-500">
          {{ t('teamEvaluators.nobody') }}
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
              @click="remove(r.evaluator_id)"
            >
              <UserMinus class="h-3.5 w-3.5" />
              {{ t('teamEvaluators.removeAction') }}
            </button>
          </li>
        </ul>
      </section>
    </template>
  </AppShell>
</template>
