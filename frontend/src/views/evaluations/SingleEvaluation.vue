<script setup lang="ts">
/**
 * The evaluator's grading surface for ONE evaluation (§6.8).
 *
 * ORCHESTRATION ONLY: load the evaluation into the store, then hand the pieces to
 * `SectionGradeCard`, `FinalizeBar` and `EvaluatorBreakdown`. No grading arithmetic, no save
 * sequencing and no isolation rules live here — those belong to the store, the service and
 * the server respectively.
 *
 * The header's team name and submitted time come from a BEST-EFFORT report fetch:
 * `EvaluationDetail` carries `report_name` but neither field, and `GET …/reports/{rid}` 403s
 * for an evaluator who is not a member of the report's team. So the extra context is
 * attempted and dropped on failure — the header degrades to the report name rather than the
 * view failing over decoration.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import SectionGradeCard from '@/views/evaluations/SectionGradeCard.vue'
import FinalizeBar from '@/views/evaluations/FinalizeBar.vue'
import EvaluatorBreakdown from '@/views/evaluations/EvaluatorBreakdown.vue'
import EvaluationHeader from '@/views/evaluations/EvaluationHeader.vue'
import AiPrecheckSlot from '@/views/evaluations/AiPrecheckSlot.vue'
import ReopenControl from '@/views/evaluations/ReopenControl.vue'
import { useEvaluationStore } from '@/stores/evaluation'
import { useAuthStore } from '@/stores/auth'
import { useGradeDraftCache } from '@/composables/useGradeDraftCache'
import { ApiError } from '@/services/http'
import { getReport } from '@/services/reports'
import { listTeams } from '@/services/teams'
import type { RouteLocationNamedRaw } from 'vue-router'

/** D9: no `GET /ai/status` exists yet (W5-8, #167), so the slot never mounts today. */
const props = withDefaults(defineProps<{ aiAvailable?: boolean }>(), { aiAvailable: false })

const CAMPAIGN_ROUTE = 'evaluation-campaign'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const store = useEvaluationStore()

const exerciseId = String(route.params.exerciseId)
const rid = String(route.params.rid)
const evid = String(route.params.evid)

const loading = ref(true)
const error = ref('')
const isForbidden = ref(false)
const teamName = ref<string | null>(null)
const submittedAt = ref<string | null>(null)
const hasStaleDraft = ref(false)

const draftCache = useGradeDraftCache(evid)

/** Template authoring order, not payload order — the evaluator reads top to bottom. */
const sections = computed(() => [...store.sections].sort((a, b) => a.position - b.position))

const canReopen = computed(() => auth.isAdmin && store.detail?.status === 'completed')

/** Null until W5-6 registers the campaign route; ViewModeSwitch disables the control then. */
const campaignTo = computed<RouteLocationNamedRaw | null>(() =>
  router.hasRoute(CAMPAIGN_ROUTE)
    ? { name: CAMPAIGN_ROUTE, params: { exerciseId, rid, evid } }
    : null,
)

/** Any section whose cached draft postdates the stored grade means unsaved work survived a
 *  reload — offer it back rather than silently overwriting it on the next save. */
function detectStaleDrafts(): void {
  hasStaleDraft.value = store.sections.some((s) =>
    draftCache.isNewerThanServer(s.report_section_id, s.grade?.updated_at ?? ''),
  )
}

async function loadReportContext(): Promise<void> {
  if (!auth.token) return
  try {
    const report = await getReport(auth.token, exerciseId, rid)
    submittedAt.value = report.submitted_at
    const teams = await listTeams(auth.token, exerciseId)
    teamName.value = teams.find((tm) => tm.id === report.team_id)?.name ?? null
  } catch {
    // Evaluators are not entitled to the report row; the header does without.
  }
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    await store.load(auth.token, exerciseId, rid, evid)
    detectStaleDrafts()
  } catch (e: unknown) {
    if (e instanceof ApiError && e.status === 403) isForbidden.value = true
    else error.value = t('evaluations.loadError')
  } finally {
    loading.value = false
  }
  await loadReportContext()
})

function discardDrafts(): void {
  for (const s of store.sections) draftCache.clear(s.report_section_id)
  hasStaleDraft.value = false
}

/** Restoring means replaying the cached inputs through the store's own validation. */
function restoreDrafts(): void {
  for (const s of store.sections) {
    const entry = draftCache.read(s.report_section_id)
    if (entry) store.setGrade(s.report_section_id, entry.value)
  }
  hasStaleDraft.value = false
}

/** A reopen publishes a new grade version, so the view re-reads rather than guessing. */
async function reload(): Promise<void> {
  if (!auth.token) return
  await store.load(auth.token, exerciseId, rid, evid)
}
</script>

<template>
  <AppShell :title="store.detail?.report_name ?? t('evaluations.title')">
    <main class="mx-auto max-w-7xl px-6 py-4">
      <p v-if="loading" class="text-sm text-[var(--rt-fg-muted)]">{{ t('evaluations.loading') }}</p>

      <p
        v-else-if="isForbidden"
        data-test="evaluation-scope"
        class="text-sm text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.scopeDenied') }}
      </p>

      <p v-else-if="error" data-test="evaluation-error" class="text-sm text-red-500">
        {{ error }}
      </p>

      <template v-else-if="store.detail">
        <EvaluationHeader
          :report-name="store.detail.report_name"
          :report-status="store.detail.report_status"
          :team-name="teamName"
          :submitted-at="submittedAt"
          :campaign-to="campaignTo"
        />

        <p
          v-if="store.needsReload"
          data-test="evaluation-reload"
          class="mb-3 rounded-md border border-[var(--rt-border)] px-3 py-2 text-xs"
        >
          {{ t('evaluations.reloadNeeded') }}
        </p>

        <aside
          v-if="hasStaleDraft"
          data-test="draft-restore"
          class="mb-3 flex flex-wrap items-center gap-3 rounded-md border border-[var(--rt-border)] px-3 py-2 text-xs"
        >
          <span>{{ t('evaluations.draftRestore') }}</span>
          <button
            data-test="draft-restore-apply"
            type="button"
            class="rounded-md bg-[var(--rt-accent)] px-2 py-1 text-white transition-opacity duration-150 hover:opacity-90"
            @click="restoreDrafts"
          >
            {{ t('evaluations.draftRestoreAction') }}
          </button>
          <button
            data-test="draft-restore-discard"
            type="button"
            class="rounded-md border border-[var(--rt-border)] px-2 py-1 transition-opacity duration-150 hover:opacity-80"
            @click="discardDrafts"
          >
            {{ t('evaluations.draftDiscardAction') }}
          </button>
        </aside>

        <div class="space-y-3">
          <template v-for="s in sections" :key="s.report_section_id">
            <SectionGradeCard :section-id="s.report_section_id" />
            <AiPrecheckSlot v-if="props.aiAvailable" :section-id="s.report_section_id" />
          </template>
        </div>

        <section class="mt-6 space-y-3">
          <EvaluatorBreakdown :exercise-id="exerciseId" :rid="rid" />

          <ReopenControl
            v-if="canReopen"
            :exercise-id="exerciseId"
            :rid="rid"
            :evid="evid"
            @reopened="reload"
          />
        </section>

        <FinalizeBar :exercise-id="exerciseId" :rid="rid" :evid="evid" />
      </template>
    </main>
  </AppShell>
</template>
