<script setup lang="ts">
/**
 * The evaluator's work queue (EV-01): what to grade, grouped by the deadline it shares.
 *
 * PRESENTATIONAL BY NECESSITY. Rows arrive as a prop rather than being fetched here, because
 * the API has no cross-report assignment listing yet: every evaluation read is scoped to one
 * `rid` (`GET /exercises/{id}/reports/{rid}/evaluations`), and `GET /exercises/{id}/reports`
 * is team-scoped, so an evaluator who is not a member of the teams they grade gets an empty
 * list from it. Until an assignment endpoint exists this view renders its empty state; the
 * container that fills `entries` is a one-line change once there is something to call.
 *
 * The AI pre-check column is opt-in via `aiAvailable` (D9): `GET /ai/status` is W5-8's, so the
 * column stays hidden rather than showing a permanently blank slot.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { groupByDeadline, type QueueEntry } from '@/lib/groupByDeadline'

const props = withDefaults(defineProps<{ entries?: QueueEntry[]; aiAvailable?: boolean }>(), {
  entries: () => [],
  aiAvailable: false,
})

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const exerciseId = computed(() => String(route.params.exerciseId))

/** Unsubmitted work has no content to grade yet, so it sits outside the deadline groups
 *  instead of padding a group the evaluator cannot act on. */
const submitted = computed(() => props.entries.filter((e) => e.submittedAt !== null))
const upcoming = computed(() => props.entries.filter((e) => e.submittedAt === null))
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
</script>

<template>
  <main class="space-y-6 p-4">
    <h1 class="text-lg font-semibold">{{ t('evaluations.queueTitle') }}</h1>

    <p
      v-if="entries.length === 0"
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
