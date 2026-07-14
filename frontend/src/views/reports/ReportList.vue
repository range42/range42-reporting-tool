<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, TriangleAlert, Clock, ShieldCheck } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import { listReports, type Report, type ReportStatus } from '@/services/reports'

const MS_PER_HOUR = 3_600_000
const MS_PER_MINUTE = 60_000
const COUNTDOWN_THRESHOLD_HOURS = 24

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

const statusBadge: Record<ReportStatus, string> = {
  draft: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  pending_approval: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  submitted: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
}

interface DueInfo {
  label: string
  soon: boolean
}

function dueInfo(dueAt: string | null): DueInfo | null {
  if (!dueAt) return null
  const ms = new Date(dueAt).getTime() - Date.now()
  if (ms <= 0) return { label: t('reports.overdue'), soon: true }
  const hours = ms / MS_PER_HOUR
  if (hours > COUNTDOWN_THRESHOLD_HOURS) {
    return { label: new Date(dueAt).toLocaleDateString(), soon: false }
  }
  const h = Math.floor(hours)
  const m = Math.floor((ms % MS_PER_HOUR) / MS_PER_MINUTE)
  return { label: t('reports.dueIn', { time: h > 0 ? `${h}h ${m}m` : `${m}m` }), soon: true }
}

function openReport(id: string): void {
  void router.push(`/exercises/${exerciseId}/reports/${id}`)
}

function createReport(): void {
  void router.push(`/exercises/${exerciseId}/reports/new`)
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
                  dueInfo(r.due_at)!.soon
                    ? 'font-medium text-amber-600 dark:text-amber-400'
                    : 'text-zinc-500',
                ]"
              >
                <Clock v-if="dueInfo(r.due_at)!.soon" class="h-3.5 w-3.5" />
                {{ dueInfo(r.due_at)!.label }}
              </span>
              <span v-else class="text-zinc-400">{{ t('reports.noDue') }}</span>
            </td>
          </tr>
          <tr v-if="reports.length === 0">
            <td colspan="4" class="px-5 py-8 text-center text-sm text-zinc-400">
              <span data-test="reports-empty">{{ t('reports.empty') }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>
