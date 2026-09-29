<script setup lang="ts">
/**
 * Global-Admin per-campaign hub: rename the campaign, and assign evaluators per team.
 *
 * Assigning someone to a team HERE (as opposed to via the standalone team screen) writes
 * BOTH halves of the intersection a report needs to auto-assign an evaluator —
 * `team_evaluator` for that team AND `campaign_evaluator` for this campaign (backend:
 * `reports.py::_auto_assign_evaluators` needs `team_evaluator ∩ campaign_evaluator`). There
 * is deliberately no separate campaign-level picker: being on this campaign's own detail page
 * already says "for this campaign," so a second, redundant "which campaign" step added
 * nothing. A duplicate `campaign_evaluator` write (assigning the same person to a second team
 * in the same campaign) 409s server-side ("already assigned") and is treated as a normal,
 * silent no-op — not an error.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import EvaluatorAssignmentPanel from '@/components/EvaluatorAssignmentPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import { listEvaluatorCandidates, type EvaluatorCandidate } from '@/services/evaluations'
import {
  addCampaignEvaluator,
  getCampaign,
  updateCampaign,
  type Campaign,
} from '@/services/campaigns'
import {
  addTeamEvaluator,
  listTeamEvaluators,
  listTeams,
  removeTeamEvaluator,
  type Team,
  type TeamEvaluatorSummary,
} from '@/services/teams'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const cid = String(route.params.cid)
const token = computed(() => auth.token ?? '')

const campaign = ref<Campaign | null>(null)
const teams = ref<Team[]>([])
const candidates = ref<EvaluatorCandidate[]>([])
const teamRows = reactive<Record<string, TeamEvaluatorSummary[]>>({})

const loading = ref(true)
const error = ref('')

const teamAssigning = reactive<Record<string, boolean>>({})
const teamAssignError = reactive<Record<string, string>>({})

const editingName = ref(false)
const nameDraft = ref('')
const nameError = ref('')
const savingName = ref(false)

async function loadCampaign(): Promise<void> {
  campaign.value = await getCampaign(token.value, exerciseId, cid)
}

async function loadTeamEvaluators(teamId: string): Promise<void> {
  teamRows[teamId] = await listTeamEvaluators(token.value, exerciseId, teamId)
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    candidates.value = await listEvaluatorCandidates(token.value, exerciseId)
    teams.value = await listTeams(token.value, exerciseId)
    await Promise.all([loadCampaign(), ...teams.value.map((tm) => loadTeamEvaluators(tm.id))])
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('campaigns.manage.loadDetailError')
  }
  loading.value = false
})

async function assignTeam(teamId: string, evaluatorId: string): Promise<void> {
  if (teamAssigning[teamId]) return
  teamAssigning[teamId] = true
  delete teamAssignError[teamId]
  try {
    await addTeamEvaluator(token.value, exerciseId, teamId, evaluatorId)
    try {
      await addCampaignEvaluator(token.value, exerciseId, cid, evaluatorId)
    } catch (e) {
      // 409 = this evaluator already covers the campaign (e.g. via another team) — expected.
      if (!(e instanceof ApiError && e.status === 409)) throw e
    }
    await loadTeamEvaluators(teamId)
  } catch (e) {
    teamAssignError[teamId] = e instanceof ApiError ? e.message : t('teamEvaluators.assignFailed')
  } finally {
    teamAssigning[teamId] = false
  }
}

async function removeTeamRow(teamId: string, evaluatorId: string): Promise<void> {
  delete teamAssignError[teamId]
  try {
    await removeTeamEvaluator(token.value, exerciseId, teamId, evaluatorId)
    await loadTeamEvaluators(teamId)
  } catch (e) {
    teamAssignError[teamId] = e instanceof ApiError ? e.message : t('teamEvaluators.removeFailed')
  }
}

function startEditName(): void {
  if (!campaign.value) return
  nameDraft.value = campaign.value.name
  nameError.value = ''
  editingName.value = true
}

function cancelEditName(): void {
  editingName.value = false
}

async function saveName(): Promise<void> {
  if (!campaign.value || nameDraft.value.trim() === '' || savingName.value) return
  savingName.value = true
  nameError.value = ''
  try {
    campaign.value = await updateCampaign(token.value, exerciseId, cid, {
      name: nameDraft.value.trim(),
    })
    editingName.value = false
  } catch (e) {
    nameError.value = e instanceof ApiError ? e.message : t('campaigns.manage.saveError')
  } finally {
    savingName.value = false
  }
}
</script>

<template>
  <AppShell :title="campaign?.name ?? t('campaigns.manage.title')">
    <template #actions>
      <RouterLink
        :to="`/exercises/${exerciseId}/campaigns`"
        class="flex h-9 items-center rounded-md px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
      >
        {{ t('campaigns.manage.backAction') }}
      </RouterLink>
    </template>

    <div v-if="error" data-test="campaign-detail-load-error" class="mb-4 text-sm text-red-500">
      {{ error }}
    </div>

    <template v-else-if="!loading && campaign">
      <div class="mb-8">
        <div v-if="!editingName" class="flex items-center gap-2">
          <h1 data-test="campaign-detail-name" class="text-2xl font-semibold tracking-tight">
            {{ campaign.name }}
          </h1>
          <button
            type="button"
            data-test="edit-campaign-name"
            class="rounded-md px-2 py-1 text-xs text-zinc-500 transition hover:bg-zinc-100 dark:hover:bg-zinc-800"
            @click="startEditName"
          >
            {{ t('campaigns.manage.editAction') }}
          </button>
        </div>
        <div v-else class="flex flex-wrap items-center gap-2">
          <label for="campaign-name-input" class="sr-only">{{
            t('campaigns.manage.nameLabel')
          }}</label>
          <input
            id="campaign-name-input"
            v-model="nameDraft"
            data-test="campaign-name-input"
            class="h-9 rounded-md border border-zinc-200 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
          <button
            type="button"
            data-test="save-campaign-name"
            :disabled="savingName"
            class="flex h-9 items-center rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
            @click="saveName"
          >
            {{ t('campaigns.manage.saveAction') }}
          </button>
          <button
            type="button"
            data-test="cancel-campaign-name"
            class="flex h-9 items-center rounded-md px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 dark:hover:bg-zinc-800"
            @click="cancelEditName"
          >
            {{ t('campaigns.manage.cancelAction') }}
          </button>
          <p v-if="nameError" data-test="campaign-name-error" class="w-full text-xs text-red-500">
            {{ nameError }}
          </p>
        </div>
      </div>

      <section>
        <h2 class="mb-1 text-sm font-semibold text-[var(--rt-fg-muted)]">
          {{ t('campaigns.manage.teamEvaluatorsHeading') }}
        </h2>
        <p class="mb-4 text-xs text-zinc-500">{{ t('campaigns.manage.teamEvaluatorsHint') }}</p>

        <div v-for="tm in teams" :key="tm.id" class="mb-8">
          <h3 :data-test="`team-heading-${tm.id}`" class="mb-2 text-sm font-medium">
            {{ tm.name }}
          </h3>
          <EvaluatorAssignmentPanel
            :rows="teamRows[tm.id] ?? []"
            :candidates="candidates"
            :assigning="teamAssigning[tm.id] ?? false"
            :assign-error="teamAssignError[tm.id] ?? ''"
            :test-prefix="`team-${tm.id}`"
            :add-heading="t('teamEvaluators.addHeading')"
            :no-candidates-text="t('teamEvaluators.noCandidates')"
            :pick-label="t('teamEvaluators.pickLabel')"
            :assign-action-text="t('teamEvaluators.assignAction')"
            :current-heading="t('teamEvaluators.currentHeading')"
            :nobody-text="t('teamEvaluators.nobody')"
            :remove-action-text="t('teamEvaluators.removeAction')"
            @assign="(evaluatorId) => assignTeam(tm.id, evaluatorId)"
            @remove="(evaluatorId) => removeTeamRow(tm.id, evaluatorId)"
          />
        </div>
      </section>
    </template>
  </AppShell>
</template>
