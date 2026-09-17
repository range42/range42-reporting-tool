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
import { RouterLink, useRoute } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import EvaluationHeader from '@/views/evaluations/EvaluationHeader.vue'
import FinalizeBar from '@/views/evaluations/FinalizeBar.vue'
import EvaluatorBreakdown from '@/views/evaluations/EvaluatorBreakdown.vue'
import CampaignNavigator from '@/views/evaluations/CampaignNavigator.vue'
import SectionJumpBar from '@/views/evaluations/SectionJumpBar.vue'
import CampaignSectionRow from '@/views/evaluations/CampaignSectionRow.vue'
import DeltaBadge from '@/views/evaluations/DeltaBadge.vue'
import { useEvaluationStore } from '@/stores/evaluation'
import { useAuthStore } from '@/stores/auth'
import { useCampaignPairing } from '@/composables/useCampaignPairing'
import { useActiveSection } from '@/composables/useActiveSection'
import { ApiError } from '@/services/http'
import type { RouteLocationNamedRaw } from 'vue-router'

const SINGLE_ROUTE = 'evaluation'

const { t } = useI18n()
const route = useRoute()
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

/** Template authoring order, not payload order. */
const sections = computed(() => [...store.sections].sort((a, b) => a.position - b.position))

const pairing = useCampaignPairing({
  token: auth.token ?? '',
  exerciseId,
  reportId: rid,
  userId: auth.user?.id ?? '',
  pinnedPrevReportId: typeof route.query.prev === 'string' ? route.query.prev : null,
})

const activeSection = useActiveSection(computed(() => sections.value.map((s) => s.section_def_id)))

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
          v-if="pairing.entries.value.length > 0"
          class="mb-4"
          :entries="pairing.entries.value"
          :current-report-id="rid"
          @select="() => {}"
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

        <div class="space-y-4">
          <CampaignSectionRow
            v-for="s in sections"
            :key="s.section_def_id"
            :section-def-id="s.section_def_id"
            :current-section-id="s.report_section_id"
            :previous-section="previousSectionFor(s.section_def_id)"
            :has-own-previous-evaluation="pairing.hasOwnPreviousEvaluation.value"
            :previous-grade="previousGradeFor(s.section_def_id)"
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
