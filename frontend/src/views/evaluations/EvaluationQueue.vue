<script setup lang="ts">
/**
 * The evaluator's work queue (EV-01): what to grade, grouped by the deadline it shares.
 *
 * Rows come from `GET /exercises/{id}/evaluations`, which returns the CALLER'S OWN
 * assignments and nobody else's. An `entries` prop still overrides the fetch, so W5-6 and
 * W5-7 can mount the same table against rows they already hold.
 *
 * The AI pre-check column is opt-in via `aiAvailable`: `GET /ai/status` is W5-8's, so the
 * column stays hidden rather than showing a permanently blank slot.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { groupByDeadline, type QueueEntry } from '@/lib/groupByDeadline'
import { listMyEvaluations, type EvaluationAssignment } from '@/services/evaluations'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'

const props = withDefaults(
  defineProps<{ entries?: QueueEntry[] | null; aiAvailable?: boolean }>(),
  { entries: null, aiAvailable: false },
)

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exerciseId = computed(() => String(route.params.exerciseId))

const fetched = ref<QueueEntry[]>([])
const loading = ref(false)
const error = ref('')

/** Wire shape -> the flat row the table and the deadline grouping read. */
function toEntry(a: EvaluationAssignment): QueueEntry {
  return {
    evaluationId: a.id,
    reportId: a.report_id,
    reportName: a.report_name,
    teamName: a.team_name,
    templateName: a.template_name,
    submittedAt: a.submitted_at,
    dueAt: a.due_at,
    gradedSectionCount: a.graded_section_count,
    gradableSectionCount: a.gradable_section_count,
  }
}

/** A caller-supplied list wins, so a parent that already holds rows skips the round trip. */
const entries = computed<QueueEntry[]>(() => props.entries ?? fetched.value)

/** Unsubmitted work has no content to grade yet, so it sits outside the deadline groups
 *  instead of padding a group the evaluator cannot act on. */
const submitted = computed(() => entries.value.filter((e) => e.submittedAt !== null))
const upcoming = computed(() => entries.value.filter((e) => e.submittedAt === null))
const groups = computed(() => groupByDeadline(submitted.value))

/** Comparing means comparing TEAMS. Two reports from one team is not a cohort. */
const isComparable = (items: QueueEntry[]): boolean =>
  new Set(items.map((i) => i.teamName)).size > 1

const when = (iso: string | null): string => (iso === null ? '' : new Date(iso).toLocaleString())

function open(e: QueueEntry): void {
  void router.push({
    name: 'evaluation',
    params: { exerciseId: exerciseId.value, rid: e.reportId, evid: e.evaluationId },
  })
}

onMounted(async () => {
  if (props.entries !== null || !auth.token) return
  loading.value = true
  try {
    fetched.value = (await listMyEvaluations(auth.token, exerciseId.value)).map(toEntry)
  } catch (e: unknown) {
    error.value = e instanceof ApiError ? e.message : t('evaluations.queueLoadError')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="space-y-6 p-4">
    <h1 class="text-lg font-semibold">{{ t('evaluations.queueTitle') }}</h1>

    <p v-if="loading" class="text-sm text-[var(--rt-fg-muted)]">{{ t('evaluations.loading') }}</p>

    <p v-else-if="error" data-test="queue-error" class="text-sm text-red-500">{{ error }}</p>

    <p
      v-else-if="entries.length === 0"
      data-test="queue-empty"
      class="text-sm text-[var(--rt-fg-muted)]"
    >
      {{ t('evaluations.queueEmpty') }}
    </p>

    <section
      v-for="group in groups"
      :key="group.dueAt ?? 'none'"
      data-test="deadline-group"
      class="space-y-2"
    >
      <header class="flex items-baseline justify-between gap-3">
        <h2 class="text-xs font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
          {{
            group.dueAt === null
              ? t('evaluations.queueNoDeadline')
              : t('evaluations.queueDue', { when: when(group.dueAt) })
          }}
        </h2>
        <button
          v-if="isComparable(group.items)"
          data-test="compare-group"
          type="button"
          class="rounded-md border border-[var(--rt-border)] px-2 py-1 text-xs transition-opacity duration-150 hover:opacity-80"
        >
          {{ t('evaluations.queueCompare') }}
        </button>
      </header>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-left text-xs text-[var(--rt-fg-muted)]">
            <tr>
              <th scope="col" class="py-1 pr-3">{{ t('evaluations.colTeam') }}</th>
              <th scope="col" class="py-1 pr-3">{{ t('evaluations.colReport') }}</th>
              <th scope="col" class="py-1 pr-3">{{ t('evaluations.colTemplate') }}</th>
              <th scope="col" class="py-1 pr-3">{{ t('evaluations.colSubmitted') }}</th>
              <th scope="col" class="py-1 pr-3">{{ t('evaluations.colProgress') }}</th>
              <th v-if="aiAvailable" scope="col" data-test="queue-ai-col" class="py-1 pr-3">
                {{ t('evaluations.colAi') }}
              </th>
              <th scope="col" class="py-1">{{ t('evaluations.colAction') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="e in group.items"
              :key="e.evaluationId"
              data-test="queue-row"
              class="border-t border-[var(--rt-border)]"
            >
              <td class="py-1.5 pr-3">{{ e.teamName }}</td>
              <td class="py-1.5 pr-3">{{ e.reportName }}</td>
              <td class="py-1.5 pr-3 text-[var(--rt-fg-muted)]">{{ e.templateName ?? '—' }}</td>
              <td :data-test="`queue-submitted-${e.evaluationId}`" class="py-1.5 pr-3">
                {{ when(e.submittedAt) }}
              </td>
              <td
                :data-test="`queue-progress-${e.evaluationId}`"
                class="py-1.5 pr-3 font-mono tabular-nums"
              >
                {{
                  t('evaluations.queueProgress', {
                    graded: e.gradedSectionCount,
                    total: e.gradableSectionCount,
                  })
                }}
              </td>
              <td
                v-if="aiAvailable"
                :data-test="`queue-ai-${e.evaluationId}`"
                class="py-1.5 pr-3 text-[var(--rt-fg-muted)]"
              >
                —
              </td>
              <td class="py-1.5">
                <button
                  :data-test="`queue-open-${e.evaluationId}`"
                  type="button"
                  class="rounded-md bg-[var(--rt-accent)] px-2 py-1 text-xs text-white transition-opacity duration-150 hover:opacity-90"
                  @click="open(e)"
                >
                  {{ t('evaluations.queueOpen') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="upcoming.length > 0" data-test="queue-upcoming" class="space-y-2">
      <h2 class="text-xs font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
        {{ t('evaluations.queueUpcoming') }}
      </h2>
      <table class="w-full text-sm">
        <thead class="text-left text-xs text-[var(--rt-fg-muted)]">
          <tr>
            <th scope="col" class="py-1 pr-3">{{ t('evaluations.colTeam') }}</th>
            <th scope="col" class="py-1 pr-3">{{ t('evaluations.colReport') }}</th>
            <th scope="col" class="py-1">{{ t('evaluations.colTemplate') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="e in upcoming"
            :key="e.evaluationId"
            data-test="queue-row"
            class="border-t border-[var(--rt-border)]"
          >
            <td class="py-1.5 pr-3">{{ e.teamName }}</td>
            <td class="py-1.5 pr-3">{{ e.reportName }}</td>
            <td class="py-1.5 text-[var(--rt-fg-muted)]">{{ e.templateName ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
