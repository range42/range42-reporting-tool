<script setup lang="ts">
/**
 * The evaluator's two-pane campaign view: the previous cycle's read-only content on the
 * left, the current (editable) evaluation on the right, one paired row per section.
 *
 * ORCHESTRATION ONLY, same rule as SingleEvaluation.vue: the current evaluation's state lives
 * in `useEvaluationStore` (D13 — no second grading store), the previous-cycle pairing lives in
 * `useCampaignPairing`, and active-section tracking lives in `useActiveSection`. This view just
 * wires the three together and hands sections to `CampaignSectionRow`.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import EvaluationHeader from '@/views/evaluations/EvaluationHeader.vue'
import FinalizeBar from '@/views/evaluations/FinalizeBar.vue'
import EvaluatorBreakdown from '@/views/evaluations/EvaluatorBreakdown.vue'
import CampaignNavigator from '@/views/evaluations/CampaignNavigator.vue'
import SectionJumpBar from '@/views/evaluations/SectionJumpBar.vue'
import CampaignSectionRow from '@/views/evaluations/CampaignSectionRow.vue'
import DeltaBadge from '@/views/evaluations/DeltaBadge.vue'
import PaneHeader from '@/views/evaluations/PaneHeader.vue'
import { parseGrade } from '@/lib/decimal'
import { useEvaluationStore } from '@/stores/evaluation'
import { useAuthStore } from '@/stores/auth'
import { useCampaignPairing } from '@/composables/useCampaignPairing'
import { useActiveSection } from '@/composables/useActiveSection'
import { useSectionMeta } from '@/composables/useSectionMeta'
import { ApiError } from '@/services/http'
import type { RouteLocationNamedRaw } from 'vue-router'

const SINGLE_ROUTE = 'evaluation'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const store = useEvaluationStore()

const exerciseId = String(route.params.exerciseId)
const rid = String(route.params.rid)
const evid = String(route.params.evid)

const loading = ref(true)
const isForbidden = ref(false)

const singleTo = computed<RouteLocationNamedRaw>(() => ({
  name: SINGLE_ROUTE,
  params: { exerciseId, rid, evid },
}))

const { metaFor } = useSectionMeta()

/** Template authoring order, not payload order. */
const sections = computed(() => [...store.sections].sort((a, b) => a.position - b.position))

/** The overall grade's scale: the sections' shared maximum, or null when they disagree. */
const overallGradeMax = computed(() => {
  const maxima = new Set(
    store.sections
      .filter((s) => s.grade_mode !== 'not_graded')
      .map((s) => parseGrade(s.grade_max))
      .filter((m): m is number => m !== null),
  )
  return maxima.size === 1 ? String([...maxima][0]) : null
})

const pairing = useCampaignPairing({
  token: auth.token ?? '',
  exerciseId,
  reportId: rid,
  userId: auth.user?.id ?? '',
  pinnedPrevReportId: typeof route.query.prev === 'string' ? route.query.prev : null,
})

const activeSection = useActiveSection(computed(() => sections.value.map((s) => s.section_def_id)))

const previousReportGrade = computed(() => pairing.previousReport.value?.overall_grade ?? null)
/** The caller's own previous grade when they evaluated it, else the report's aggregate. */
const previousHeaderGrade = computed(() =>
  pairing.hasOwnPreviousEvaluation.value
    ? pairing.previousOverallGrade.value
    : previousReportGrade.value,
)

function previousSectionFor(sectionDefId: string) {
  return (
    pairing.previousReport.value?.sections.find((s) => s.section_def_id === sectionDefId) ?? null
  )
}

function previousGradeFor(sectionDefId: string) {
  const prevSection = previousSectionFor(sectionDefId)
  if (!prevSection) return null
  return pairing.previousGrades.value?.find((g) => g.report_section_id === prevSection.id) ?? null
}

/** Pins an earlier report as the previous pane, keeping the choice in `?prev=`. */
async function pinPrevious(reportId: string): Promise<void> {
  void router.replace({ query: { ...route.query, prev: reportId } })
  await pairing.load(reportId)
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    await store.load(auth.token, exerciseId, rid, evid)
    await pairing.load()
  } catch (e: unknown) {
    if (e instanceof ApiError && e.status === 403) isForbidden.value = true
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => activeSection.disconnect())
</script>

<template>
  <AppShell :title="store.detail?.report_name ?? t('evaluations.title')">
    <main class="mx-auto max-w-[1800px] px-6 py-4">
      <p v-if="loading" class="text-sm text-[var(--rt-fg-muted)]">{{ t('evaluations.loading') }}</p>

      <p
        v-else-if="isForbidden || pairing.status.value === 'forbidden'"
        data-test="evaluation-scope"
        class="text-sm text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.scopeDenied') }}
      </p>

      <div
        v-else-if="pairing.status.value === 'no_campaign'"
        data-test="no-campaign"
        class="space-y-2"
      >
        <p class="text-sm text-[var(--rt-fg-muted)]">{{ t('evaluations.campaignNoCampaign') }}</p>
        <RouterLink
          data-test="mode-single"
          :to="singleTo"
          class="text-sm text-[var(--rt-accent)] underline"
        >
          {{ t('evaluations.campaignBackToSingle') }}
        </RouterLink>
      </div>

      <template v-else-if="store.detail">
        <EvaluationHeader
          :report-name="store.detail.report_name"
          :report-status="store.detail.report_status"
          :team-name="store.detail.team_name"
          :submitted-at="store.detail.submitted_at"
          :campaign-to="null"
          mode="campaign"
          :single-to="singleTo"
        />

        <CampaignNavigator
          v-if="pairing.teamEntries.value.length > 0"
          class="mb-4"
          :entries="pairing.teamEntries.value"
          :current-report-id="rid"
          :pinned-report-id="pairing.previousEntry.value?.report_id ?? null"
          @select="pinPrevious"
        />

        <SectionJumpBar
          class="mb-4"
          :sections="sections.map((s) => ({ section_def_id: s.section_def_id, name: s.name }))"
          :active-section-id="activeSection.activeSectionId.value"
          @jump="activeSection.jumpTo"
        />

        <p
          v-if="pairing.status.value === 'no_previous'"
          data-test="campaign-empty"
          class="mb-4 text-xs italic text-[var(--rt-fg-muted)]"
        >
          {{ t('evaluations.campaignFirstReport') }}
        </p>

        <div data-test="pane-headers" class="mb-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <PaneHeader
            v-if="pairing.previousEntry.value"
            data-test="pane-header-previous"
            :label="t('evaluations.campaignPanePrevious')"
            :report-name="pairing.previousEntry.value.name"
            :team-name="pairing.previousEntry.value.team_name"
            :overall-grade="previousHeaderGrade"
            :grade-max="overallGradeMax"
          />
          <div v-else aria-hidden="true" class="hidden md:block" />
          <PaneHeader
            data-test="pane-header-current"
            :label="t('evaluations.campaignPaneCurrent')"
            :report-name="store.detail.report_name"
            :team-name="store.detail.team_name"
            :overall-grade="store.detail.overall_grade"
            :grade-max="overallGradeMax"
            is-current
          />
        </div>

        <div class="space-y-4">
          <CampaignSectionRow
            v-for="s in sections"
            :key="s.section_def_id"
            :section-def-id="s.section_def_id"
            :current-section-id="s.report_section_id"
            :previous-section="previousSectionFor(s.section_def_id)"
            :has-own-previous-evaluation="pairing.hasOwnPreviousEvaluation.value"
            :previous-grade="previousGradeFor(s.section_def_id)"
            :previous-report-grade="previousReportGrade"
            :meta="metaFor(s)"
            @register-row="(el) => activeSection.registerRow(s.section_def_id, el)"
          />
        </div>

        <section class="mt-6 space-y-3">
          <EvaluatorBreakdown :exercise-id="exerciseId" :rid="rid" />
        </section>

        <FinalizeBar :exercise-id="exerciseId" :rid="rid" :evid="evid">
          <template #vs-previous>
            <DeltaBadge
              :current="store.detail.overall_grade"
              :previous="pairing.previousOverallGrade.value"
            />
          </template>
        </FinalizeBar>
      </template>
    </main>
  </AppShell>
</template>
