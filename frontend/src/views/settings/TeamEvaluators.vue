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
import AppShell from '@/components/AppShell.vue'
import EvaluatorAssignmentPanel from '@/components/EvaluatorAssignmentPanel.vue'
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
const loading = ref(true)
const error = ref('')
const assignError = ref('')
const assigning = ref(false)

async function load(): Promise<void> {
  rows.value = await listTeamEvaluators(token.value, exerciseId, teamId)
}

async function assign(evaluatorId: string): Promise<void> {
  if (assigning.value) return
  assigning.value = true
  assignError.value = ''
  try {
    await addTeamEvaluator(token.value, exerciseId, teamId, evaluatorId)
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

    <EvaluatorAssignmentPanel
      v-else
      :rows="rows"
      :candidates="candidates"
      :assigning="assigning"
      :assign-error="assignError"
      :add-heading="t('teamEvaluators.addHeading')"
      :no-candidates-text="t('teamEvaluators.noCandidates')"
      :pick-label="t('teamEvaluators.pickLabel')"
      :assign-action-text="t('teamEvaluators.assignAction')"
      :current-heading="t('teamEvaluators.currentHeading')"
      :nobody-text="t('teamEvaluators.nobody')"
      :remove-action-text="t('teamEvaluators.removeAction')"
      @assign="assign"
      @remove="remove"
    />
  </AppShell>
</template>
