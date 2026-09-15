<script setup lang="ts">
/**
 * Global-Admin assignment screen: who evaluates this report.
 *
 * This is the manual, per-report path — the one that hands a submitted report to an evaluator
 * so it appears in their queue. Assignment does NOT start the evaluation: the report's status
 * moves on the evaluator's first write, not here.
 *
 * Candidates come from the exercise's evaluator roles, so a name offered here is one the
 * assign endpoint will accept. Removals are soft and keep the removed evaluator visible with
 * their reason, because the aggregate they contributed to has to stay explicable.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { UserPlus } from '@lucide/vue'
import AppShell from '@/components/AppShell.vue'
import UnassignControl from '@/views/reports/UnassignControl.vue'
import {
  assignEvaluator,
  listEvaluationsForReport,
  listEvaluatorCandidates,
  type EvaluationBreakdown,
  type EvaluatorCandidate,
} from '@/services/evaluations'
import { getReport } from '@/services/reports'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const rid = String(route.params.rid)

const breakdown = ref<EvaluationBreakdown | null>(null)
const candidates = ref<EvaluatorCandidate[]>([])
const reportName = ref('')
const picked = ref('')
const loading = ref(true)
const error = ref('')
const assignError = ref('')
const assigning = ref(false)

const rows = computed(() => breakdown.value?.evaluations ?? [])
const active = computed(() => rows.value.filter((r) => r.unassigned_at === null))

/** Someone already holding an ACTIVE seat is not offerable; a previously removed evaluator is,
 *  because assigning them again revives their original row rather than duplicating it. */
const offerable = computed(() =>
  candidates.value.filter((c) => !active.value.some((r) => r.evaluator_id === c.user_id)),
)

async function load(): Promise<void> {
  if (!auth.token) return
  try {
    breakdown.value = await listEvaluationsForReport(auth.token, exerciseId, rid)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('evaluations.loadError')
  }
}

async function assign(): Promise<void> {
  if (!auth.token || picked.value === '' || assigning.value) return
  assigning.value = true
  assignError.value = ''
  try {
    await assignEvaluator(auth.token, exerciseId, rid, picked.value)
    picked.value = ''
    await load()
  } catch (e) {
    assignError.value = e instanceof ApiError ? e.message : t('evaluations.assignFailed')
  } finally {
    assigning.value = false
  }
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    const [report, people] = await Promise.all([
      getReport(auth.token, exerciseId, rid),
      listEvaluatorCandidates(auth.token, exerciseId),
    ])
    reportName.value = report.name
    candidates.value = people
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('evaluations.loadError')
  }
  await load()
  loading.value = false
})
</script>

<template>
  <AppShell :title="t('evaluations.assignTitle')">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('evaluations.assignTitle') }}</h1>
      <p v-if="reportName" data-test="assign-report-name" class="mt-1 text-sm text-zinc-500">
        {{ reportName }}
      </p>
    </div>

    <p v-if="loading" data-test="assign-loading" class="text-sm text-[var(--rt-fg-muted)]">
      {{ t('evaluations.loading') }}
    </p>

    <p v-else-if="error" data-test="assign-load-error" class="text-sm text-red-500">{{ error }}</p>

    <template v-else>
      <section class="mb-8 space-y-2">
        <h2 class="text-xs font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
          {{ t('evaluations.assignAddHeading') }}
        </h2>

        <p
          v-if="candidates.length === 0"
          data-test="assign-no-candidates"
          class="text-sm text-[var(--rt-fg-muted)]"
        >
          {{ t('evaluations.assignNoCandidates') }}
        </p>

        <div v-else class="flex flex-wrap items-center gap-2">
          <label for="assign-pick" class="sr-only">{{ t('evaluations.assignPickLabel') }}</label>
          <select
            id="assign-pick"
            v-model="picked"
            data-test="assign-pick"
            class="h-9 rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] px-2 text-sm"
          >
            <option value="">{{ t('evaluations.assignPickLabel') }}</option>
            <option v-for="c in offerable" :key="c.user_id" :value="c.user_id">
              {{ c.display_name }} ({{ c.email }})
            </option>
          </select>
          <button
            data-test="assign-submit"
            type="button"
            :disabled="picked === '' || assigning"
            class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition disabled:opacity-50 hover:bg-indigo-400"
            @click="assign"
          >
            <UserPlus class="h-4 w-4" />
            {{ t('evaluations.assignAction') }}
          </button>
        </div>

        <p v-if="assignError" data-test="assign-error" class="text-sm text-red-500">
          {{ assignError }}
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="text-xs font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
          {{ t('evaluations.assignCurrentHeading') }}
        </h2>

        <p
          v-if="rows.length === 0"
          data-test="assign-none"
          class="text-sm text-[var(--rt-fg-muted)]"
        >
          {{ t('evaluations.assignNobody') }}
        </p>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="text-left text-xs text-[var(--rt-fg-muted)]">
              <tr>
                <th scope="col" class="py-1 pr-3">{{ t('evaluations.colEvaluator') }}</th>
                <th scope="col" class="py-1 pr-3">{{ t('evaluations.colGrade') }}</th>
                <th scope="col" class="py-1">{{ t('evaluations.colAction') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in rows"
                :key="r.id"
                :data-test="`assign-row-${r.id}`"
                class="border-t border-[var(--rt-border)] align-top"
              >
                <td class="py-1.5 pr-3">
                  {{ r.evaluator_display_name ?? t('evaluations.unnamedEvaluator') }}
                  <span
                    v-if="r.unassigned_at !== null"
                    :data-test="`assign-removed-${r.id}`"
                    class="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    {{ t('evaluations.unassignedBadge') }}
                  </span>
                  <p
                    v-if="r.unassign_reason"
                    class="mt-0.5 text-xs italic text-[var(--rt-fg-muted)]"
                  >
                    {{ r.unassign_reason }}
                  </p>
                </td>
                <td class="py-1.5 pr-3 font-mono tabular-nums">{{ r.overall_grade ?? '—' }}</td>
                <td class="py-1.5">
                  <UnassignControl
                    v-if="r.unassigned_at === null"
                    :exercise-id="exerciseId"
                    :rid="rid"
                    :evid="r.id"
                    @unassigned="load"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </AppShell>
</template>
