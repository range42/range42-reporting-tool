<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, TriangleAlert, Clock, ShieldCheck, ClipboardCheck, CalendarPlus } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import { listReports, type Report, type ReportStatus } from '@/services/reports'
import { useCountdown, type CountdownInfo } from '@/composables/useCountdown'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const caps = useCapabilitiesStore()

const exerciseId = route.params.exerciseId as string
const reports = ref<Report[]>([])
const loading = ref(true)
const error = ref('')

const token = computed(() => auth.token ?? '')
const canApprove = computed(() => auth.isAdmin || caps.canApproveReports(exerciseId))
const canEvaluate = computed(() => auth.isAdmin || caps.canEvaluate(exerciseId))

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    // Populate capabilities so the approvals affordance + guard resolve for this exercise.
    await caps.load(token.value, exerciseId).catch(() => undefined)
    reports.value = await listReports(token.value, exerciseId)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.loadError')
  } finally {
    loading.value = false
  }
})

function openApprovals(): void {
  void router.push(`/exercises/${exerciseId}/reports/approvals`)
}

function openEvaluations(): void {
  void router.push({ name: 'evaluation-queue', params: { exerciseId } })
}

const statusBadge: Record<ReportStatus, string> = {
  draft: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  pending_approval: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  submitted: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  under_evaluation: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300',
  evaluated: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
}

const countdown = useCountdown(t)

function dueInfo(dueAt: string | null): CountdownInfo | null {
  return countdown.info(dueAt)
}

// Today's list styling only distinguishes "needs attention" (amber) from a
// plain date; soon and critical both map to the former.
function dueSoon(dueAt: string | null): boolean {
  const due = dueInfo(dueAt)
  return due !== null && due.urgency !== 'none'
}

/** Mirrors the backend's assignable set: an evaluator can only be put on a report that has
 *  actually been submitted. Assigning does not start the evaluation. */
const ASSIGNABLE_STATUSES: readonly string[] = ['submitted', 'under_evaluation']

const canAssign = (status: string): boolean => ASSIGNABLE_STATUSES.includes(status)

function openEvaluators(id: string): void {
  void router.push({ name: 'report-evaluators', params: { exerciseId, rid: id } })
}

/** Opens unconditionally — no status gating. The evaluation-summary page itself decides
 *  whether to show content-only (not yet evaluated) or content plus scores. */
function openEvaluationSummary(id: string): void {
  void router.push({ name: 'report-evaluation-summary', params: { exerciseId, rid: id } })
}

function openReport(id: string): void {
  void router.push(`/exercises/${exerciseId}/reports/${id}`)
}

function createReport(): void {
  void router.push(`/exercises/${exerciseId}/reports/new`)
}

function createCampaign(): void {
  void router.push(`/exercises/${exerciseId}/campaigns/new`)
}
</script>

<template>
  <AppShell :title="t('reports.title')">
    <template #actions>
      <button
        v-if="canApprove"
        type="button"
        data-test="approvals-link"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800/60"
        @click="openApprovals"
      >
        <ShieldCheck class="h-4 w-4" />
        {{ t('reports.approvals.nav') }}
      </button>
      <button
        v-if="canEvaluate"
        type="button"
        data-test="evaluations-link"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800/60"
        @click="openEvaluations"
      >
        <ClipboardCheck class="h-4 w-4" />
        {{ t('evaluations.nav') }}
      </button>
      <button
        v-if="auth.isAdmin"
        type="button"
        data-test="new-campaign"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800/60"
        @click="createCampaign"
      >
        <CalendarPlus class="h-4 w-4" />
        {{ t('campaigns.new') }}
      </button>
      <button
        v-if="auth.isAdmin"
        type="button"
        data-test="new-report"
        class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400"
        @click="createReport"
      >
        <Plus class="h-4 w-4" />
        {{ t('reports.new') }}
      </button>
    </template>

    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('reports.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('reports.subtitle') }}</p>
    </div>

    <div
      v-if="error"
      class="alert-error mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div v-if="loading" class="flex justify-center py-16 text-zinc-500">
      <Clock class="h-5 w-5 animate-spin" />
    </div>

    <div
      v-else
      class="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
    >
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-zinc-200 text-left dark:border-zinc-800">
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('reports.name') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('reports.status') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('reports.sections') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('reports.due') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500" />
            <th
              v-if="auth.isAdmin"
              class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500"
            >
              {{ t('reports.evaluators') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in reports"
            :key="r.id"
            data-test="report-row"
            class="cursor-pointer border-b border-zinc-100 transition last:border-0 hover:bg-zinc-50 dark:border-zinc-800/60 dark:hover:bg-zinc-800/40"
            @click="openReport(r.id)"
          >
            <td class="px-5 py-3 font-medium">{{ r.name }}</td>
            <td class="px-5 py-3">
              <span
                :class="[
                  'rounded px-1.5 py-0.5 text-[11px] font-medium',
                  statusBadge[r.status] ?? statusBadge.draft,
                ]"
              >
                {{ t(`reports.statusLabel.${r.status}`) }}
              </span>
            </td>
            <td class="px-5 py-3 text-zinc-500">{{ r.section_count }}</td>
            <td class="px-5 py-3">
              <span
                v-if="dueInfo(r.due_at)"
                :class="[
                  'inline-flex items-center gap-1',
                  dueSoon(r.due_at)
                    ? 'font-medium text-amber-600 dark:text-amber-400'
                    : 'text-zinc-500',
                ]"
              >
                <Clock v-if="dueSoon(r.due_at)" class="h-3.5 w-3.5" />
                {{ dueInfo(r.due_at)!.label }}
              </span>
              <span v-else class="text-zinc-400">{{ t('reports.noDue') }}</span>
            </td>
            <td class="px-5 py-3">
              <button
                :data-test="`view-evaluation-${r.id}`"
                type="button"
                class="rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium transition hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/60"
                @click.stop="openEvaluationSummary(r.id)"
              >
                {{ t('reports.viewEvaluation') }}
              </button>
            </td>
            <td v-if="auth.isAdmin" class="px-5 py-3">
              <button
                v-if="canAssign(r.status)"
                :data-test="`assign-evaluators-${r.id}`"
                type="button"
                class="rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium transition hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/60"
                @click.stop="openEvaluators(r.id)"
              >
                {{ t('reports.manageEvaluators') }}
              </button>
            </td>
          </tr>
          <tr v-if="reports.length === 0">
            <td :colspan="auth.isAdmin ? 6 : 5" class="px-5 py-8 text-center text-sm text-zinc-400">
              <span data-test="reports-empty">{{ t('reports.empty') }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>
