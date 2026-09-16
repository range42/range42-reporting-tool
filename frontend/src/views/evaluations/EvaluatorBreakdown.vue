<script setup lang="ts">
/**
 * Who has graded this report, and how their work aggregates.
 *
 * TWO AUDIENCES, ONE ENDPOINT. `GET .../reports/{rid}/evaluations` is scoped server-side:
 * a Global Admin's response carries every evaluator's row, an evaluator's carries exactly
 * their own. The `isAdmin` branch below only chooses a LAYOUT — the full table versus own
 * row plus the report aggregate.
 *
 * THE SERVER IS THE REAL BOUNDARY. The client-side filter to `evaluator_id === me` is UI
 * hygiene, not the security control: it protects against rendering a peer's row if a future
 * endpoint change ever widens the payload, and nothing more. Never move an isolation rule
 * here — a check that lives only in the client is a check an API call walks past.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { listEvaluationsForReport, type EvaluationBreakdown } from '@/services/evaluations'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ exerciseId: string; rid: string }>()

const { t } = useI18n()
const auth = useAuthStore()

const data = ref<EvaluationBreakdown | null>(null)
const failed = ref(false)

const rows = computed(() => {
  const all = data.value?.evaluations ?? []
  if (auth.isAdmin) return all
  return all.filter((r) => r.evaluator_id === auth.user?.id)
})

const dash = '—'
const finalizedAt = (iso: string | null): string =>
  iso === null ? t('evaluations.notYet') : new Date(iso).toLocaleString()

onMounted(async () => {
  if (!auth.token) return
  try {
    data.value = await listEvaluationsForReport(auth.token, props.exerciseId, props.rid)
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <section v-if="data" data-test="breakdown" class="space-y-2">
    <h2 class="text-xs font-medium uppercase tracking-wider text-[var(--rt-fg-muted)]">
      {{ auth.isAdmin ? t('evaluations.breakdownHeading') : t('evaluations.breakdownYours') }}
    </h2>

    <div class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead class="text-left text-[var(--rt-fg-muted)]">
          <tr>
            <th v-if="auth.isAdmin" scope="col" class="py-1 pr-3">
              {{ t('evaluations.colEvaluator') }}
            </th>
            <th scope="col" class="py-1 pr-3">{{ t('evaluations.colGrade') }}</th>
            <th scope="col" class="py-1 pr-3">{{ t('evaluations.colCompleted') }}</th>
            <th scope="col" class="py-1 pr-3">{{ t('evaluations.colReopens') }}</th>
            <th scope="col" class="py-1">{{ t('evaluations.colWeight') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in rows"
            :key="r.id"
            :data-test="`breakdown-row-${r.id}`"
            class="border-t border-[var(--rt-border)]"
          >
            <td v-if="auth.isAdmin" class="py-1 pr-3">
              {{ r.evaluator_display_name ?? t('evaluations.unnamedEvaluator') }}
            </td>
            <td :data-test="`breakdown-grade-${r.id}`" class="py-1 pr-3 font-mono tabular-nums">
              {{ r.overall_grade ?? dash }}
            </td>
            <td :data-test="`breakdown-completed-${r.id}`" class="py-1 pr-3">
              {{ finalizedAt(r.completed_at) }}
            </td>
            <td :data-test="`breakdown-reopens-${r.id}`" class="py-1 pr-3 tabular-nums">
              {{ r.reopen_count }}
            </td>
            <td :data-test="`breakdown-weight-${r.id}`" class="py-1 font-mono tabular-nums">
              {{ r.aggregated_weight }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- The report-level aggregate is identical for every caller allowed to see it at all;
         the headcount is a cardinality, not an identity, so it is not suppressed. -->
    <p data-test="breakdown-aggregate" class="flex items-baseline gap-2 text-xs">
      <span class="text-[var(--rt-fg-muted)]">{{ t('evaluations.breakdownAggregate') }}</span>
      <span class="font-mono tabular-nums">{{ data.aggregate.overall_grade ?? dash }}</span>
    </p>
  </section>
</template>
