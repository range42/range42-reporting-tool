<script setup lang="ts">
/**
 * Global-Admin view of reports stuck in `under_evaluation`, most stalled first.
 *
 * Read-only: the server ranks the rows; each row leads to the report's evaluator screen,
 * where the finalize-on-behalf and unassign actions live.
 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Clock, Hourglass, Inbox, TriangleAlert, UserX } from '@lucide/vue'
import AppShell from '@/components/AppShell.vue'
import { listStalledReports, type StalledReports } from '@/services/evaluations'
import { ApiError } from '@/services/http'
import { useAuthStore } from '@/stores/auth'

const MS_PER_DAY = 86_400_000

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)

const data = ref<StalledReports | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    data.value = await listStalledReports(auth.token, exerciseId)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('evaluations.stalled.loadError')
  } finally {
    loading.value = false
  }
})

/** Whole days elapsed since `iso`, never negative. */
function daysSince(iso: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / MS_PER_DAY))
}

function waitedFor(iso: string | null): string {
  return iso === null
    ? t('evaluations.stalled.unknown')
    : t('evaluations.stalled.days', daysSince(iso))
}

function open(rid: string): void {
  void router.push({ name: 'report-evaluators', params: { exerciseId, rid } })
}
</script>

<template>
  <AppShell :title="t('evaluations.stalled.title')">
    <header class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('evaluations.stalled.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('evaluations.stalled.subtitle') }}</p>
      <p v-if="data" data-test="stalled-policy" class="mt-2 text-xs text-zinc-500">
        <span class="font-medium uppercase tracking-wider">
          {{ t('evaluations.stalled.policyLabel') }}:
        </span>
        {{ t(`evaluations.stalled.policy.${data.finalize_policy}`) }}
      </p>
    </header>

    <div
      v-if="error"
      data-test="stalled-error"
      class="mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div v-if="loading" class="flex justify-center py-16 text-zinc-500">
      <Clock class="h-5 w-5 animate-spin" />
    </div>

    <template v-else-if="data">
      <p
        v-if="data.reports.length === 0"
        data-test="stalled-empty"
        class="flex flex-col items-center gap-2 rounded-lg border border-dashed border-zinc-300 py-10 text-sm text-zinc-400 dark:border-zinc-700"
      >
        <Inbox class="h-6 w-6" />
        {{ t('evaluations.stalled.empty') }}
      </p>

      <ol v-else class="space-y-2">
        <li
          v-for="r in data.reports"
          :key="r.report_id"
          data-test="stalled-row"
          :class="[
            'grid gap-3 rounded-lg border bg-white px-4 py-3 dark:bg-zinc-900 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center',
            r.oldest_pending_activity_at === null
              ? 'border-red-500/40'
              : 'border-zinc-200 dark:border-zinc-800',
          ]"
        >
          <div class="min-w-0">
            <p data-test="stalled-name" class="truncate font-medium">{{ r.report_name }}</p>
            <p class="truncate text-xs text-zinc-500">
              {{ t('evaluations.stalled.team') }}: {{ r.team_name }}
            </p>
            <dl class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
              <div class="flex gap-1">
                <dt class="text-zinc-500">{{ t('evaluations.stalled.waiting') }}</dt>
                <dd class="font-medium tabular-nums">{{ waitedFor(r.under_evaluation_since) }}</dd>
              </div>
              <div class="flex gap-1">
                <dt class="text-zinc-500">{{ t('evaluations.stalled.finalized') }}</dt>
                <dd class="font-medium tabular-nums">
                  {{
                    t('evaluations.stalled.finalizedCount', {
                      completed: r.completed_evaluator_count,
                      counted: r.counted_evaluator_count,
                    })
                  }}
                </dd>
              </div>
              <div class="flex gap-1">
                <dt class="text-zinc-500">{{ t('evaluations.stalled.lastActivity') }}</dt>
                <dd
                  v-if="r.oldest_pending_activity_at"
                  class="flex items-center gap-1 font-medium tabular-nums text-amber-700 dark:text-amber-300"
                >
                  <Hourglass class="h-3 w-3" />
                  {{ t('evaluations.stalled.daysAgo', daysSince(r.oldest_pending_activity_at)) }}
                </dd>
                <dd
                  v-else
                  class="flex items-center gap-1 font-medium text-red-600 dark:text-red-400"
                >
                  <UserX class="h-3 w-3" />
                  {{ t('evaluations.stalled.noPendingEvaluator') }}
                </dd>
              </div>
            </dl>
          </div>
          <button
            type="button"
            data-test="stalled-open"
            class="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800/60"
            @click="open(r.report_id)"
          >
            {{ t('evaluations.stalled.open') }}
          </button>
        </li>
      </ol>
    </template>
  </AppShell>
</template>
