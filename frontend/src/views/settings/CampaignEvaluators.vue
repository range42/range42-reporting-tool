<script setup lang="ts">
/**
 * Global-Admin assignment screen: which evaluator(s) cover this campaign.
 *
 * Independent of team — see TeamEvaluators.vue for the other half. A report only auto-assigns
 * an evaluator once both halves match for its team and campaign
 * (backend: reports.py::_auto_assign_evaluators).
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
  addCampaignEvaluator,
  listCampaignEvaluators,
  removeCampaignEvaluator,
  type CampaignEvaluatorSummary,
} from '@/services/campaigns'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const campaignId = String(route.params.campaignId)
const token = computed(() => auth.token ?? '')

const rows = ref<CampaignEvaluatorSummary[]>([])
const candidates = ref<EvaluatorCandidate[]>([])
const loading = ref(true)
const error = ref('')
const assignError = ref('')
const assigning = ref(false)

async function load(): Promise<void> {
  rows.value = await listCampaignEvaluators(token.value, exerciseId, campaignId)
}

async function assign(evaluatorId: string): Promise<void> {
  if (assigning.value) return
  assigning.value = true
  assignError.value = ''
  try {
    await addCampaignEvaluator(token.value, exerciseId, campaignId, evaluatorId)
    await load()
  } catch (e) {
    assignError.value = e instanceof ApiError ? e.message : t('campaignEvaluators.assignFailed')
  } finally {
    assigning.value = false
  }
}

async function remove(evaluatorId: string): Promise<void> {
  assignError.value = ''
  try {
    await removeCampaignEvaluator(token.value, exerciseId, campaignId, evaluatorId)
    await load()
  } catch (e) {
    assignError.value = e instanceof ApiError ? e.message : t('campaignEvaluators.removeFailed')
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
    error.value = e instanceof ApiError ? e.message : t('campaignEvaluators.loadError')
  }
  loading.value = false
})
</script>

<template>
  <AppShell :title="t('campaignEvaluators.title')">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('campaignEvaluators.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('campaignEvaluators.subtitle') }}</p>
    </div>

    <p v-if="loading" data-test="assign-loading" class="text-sm text-zinc-500">
      {{ t('campaignEvaluators.loading') }}
    </p>

    <p v-else-if="error" data-test="assign-load-error" class="text-sm text-red-500">{{ error }}</p>

    <EvaluatorAssignmentPanel
      v-else
      :rows="rows"
      :candidates="candidates"
      :assigning="assigning"
      :assign-error="assignError"
      :add-heading="t('campaignEvaluators.addHeading')"
      :no-candidates-text="t('campaignEvaluators.noCandidates')"
      :pick-label="t('campaignEvaluators.pickLabel')"
      :assign-action-text="t('campaignEvaluators.assignAction')"
      :current-heading="t('campaignEvaluators.currentHeading')"
      :nobody-text="t('campaignEvaluators.nobody')"
      :remove-action-text="t('campaignEvaluators.removeAction')"
      @assign="assign"
      @remove="remove"
    />
  </AppShell>
</template>
