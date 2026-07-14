<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Check, X, Clock, ShieldCheck, Inbox, TriangleAlert } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import {
  listPendingApproval,
  getReport,
  approveReport,
  rejectReport,
  type Report,
  type ReportDetail,
} from '@/services/reports'

type StepState = 'done' | 'current' | 'pending'
interface StepView {
  index: number
  label: string
  required: boolean
  state: StepState
}

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const caps = useCapabilitiesStore()

const exerciseId = route.params.exerciseId as string
const token = computed(() => auth.token ?? '')

const queue = ref<Report[]>([])
const selected = ref<ReportDetail | null>(null)
const loading = ref(true)
const error = ref('')
const note = ref('')
const acting = ref(false)
const decisionError = ref('')

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    // Load capabilities so the requiresApprover guard resolves on subsequent nav.
    await caps.load(token.value, exerciseId)
    queue.value = await listPendingApproval(token.value, exerciseId)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.approvals.loadError')
  } finally {
    loading.value = false
  }
})

async function select(id: string): Promise<void> {
  note.value = ''
  decisionError.value = ''
  selected.value = await getReport(token.value, exerciseId, id)
}

const canAct = computed(
  () => selected.value !== null && (selected.value.can_approve || auth.isAdmin),
)

const steps = computed<StepView[]>(() => {
  const d = selected.value
  if (!d) return []
  const entries = d.approval_chain ?? []
  const approved = new Set(
    d.approval_records.filter((r) => r.action === 'approved').map((r) => r.step),
  )
  const count = entries.length || 1
  const requiredIdx = entries.length ? entries.flatMap((e, i) => (e.required ? [i + 1] : [])) : [1]
  const current = requiredIdx.filter((i) => !approved.has(i)).sort((a, b) => a - b)[0] ?? -1
  return Array.from({ length: count }, (_, k) => {
    const index = k + 1
    const state: StepState = approved.has(index)
      ? 'done'
      : index === current
        ? 'current'
        : 'pending'
    return {
      index,
      label: t('reports.approvals.stepLabel', { n: index }),
      required: entries[k]?.required ?? true,
      state,
    }
  })
})

async function decide(kind: 'approve' | 'reject'): Promise<void> {
  const d = selected.value
  if (!d || acting.value) return
  const comment = note.value.trim()
  if (kind === 'reject' && !comment) return
  acting.value = true
  decisionError.value = ''
  try {
    if (kind === 'approve') {
      await approveReport(token.value, exerciseId, d.id, comment ? { comment } : {})
    } else {
      await rejectReport(token.value, exerciseId, d.id, { comment })
    }
    selected.value = null
    note.value = ''
    queue.value = await listPendingApproval(token.value, exerciseId)
  } catch (e) {
    decisionError.value = e instanceof ApiError ? e.message : t('reports.approvals.decisionError')
  } finally {
    acting.value = false
  }
}

const stepDot: Record<StepState, string> = {
  done: 'bg-emerald-500 text-white',
  current: 'bg-amber-500 text-white ring-4 ring-amber-500/20',
  pending: 'bg-zinc-200 text-zinc-500 dark:bg-zinc-700 dark:text-zinc-400',
}
</script>

<template>
  <AppShell :title="t('reports.approvals.title')">
    <header class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('reports.approvals.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('reports.approvals.subtitle') }}</p>
    </header>

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

    <div v-else class="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <!-- Queue rail -->
      <aside class="lg:sticky lg:top-4 lg:self-start">
        <h2 class="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
          {{ t('reports.approvals.queue') }}
          <span class="ml-1 text-zinc-400">{{ queue.length }}</span>
        </h2>
        <ul class="space-y-1.5">
          <li v-for="r in queue" :key="r.id">
            <button
              type="button"
              data-test="queue-item"
              :class="[
                'flex w-full items-center gap-3 rounded-lg border px-3.5 py-3 text-left transition',
                selected?.id === r.id
                  ? 'border-amber-500/50 bg-amber-50 dark:bg-amber-500/10'
                  : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/40',
              ]"
              @click="select(r.id)"
            >
              <span
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-amber-600 dark:text-amber-400"
              >
                <Clock class="h-4 w-4" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium">{{ r.name }}</span>
                <span class="block text-xs text-zinc-500">{{
                  t('reports.statusLabel.pending_approval')
                }}</span>
              </span>
            </button>
          </li>
          <li
            v-if="queue.length === 0"
            data-test="approvals-empty"
            class="flex flex-col items-center gap-2 rounded-lg border border-dashed border-zinc-300 py-10 text-sm text-zinc-400 dark:border-zinc-700"
          >
            <Inbox class="h-6 w-6" />
            {{ t('reports.approvals.empty') }}
          </li>
        </ul>
      </aside>

      <!-- Decision pane -->
      <section>
        <div
          v-if="!selected"
          data-test="select-prompt"
          class="flex h-full min-h-64 items-center justify-center rounded-xl border border-dashed border-zinc-300 text-sm text-zinc-400 dark:border-zinc-700"
        >
          {{ t('reports.approvals.selectPrompt') }}
        </div>

        <div
          v-else
          class="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
        >
          <div class="border-b border-zinc-100 px-6 py-5 dark:border-zinc-800">
            <h3 class="text-lg font-semibold tracking-tight">{{ selected.name }}</h3>
            <p v-if="selected.description" class="mt-1 text-sm text-zinc-500">
              {{ selected.description }}
            </p>
          </div>

          <!-- Approval chain -->
          <div class="border-b border-zinc-100 px-6 py-5 dark:border-zinc-800">
            <h4 class="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('reports.approvals.chain') }}
            </h4>
            <ol class="flex flex-wrap items-center gap-x-2 gap-y-3">
              <li
                v-for="s in steps"
                :key="s.index"
                data-test="chain-step"
                class="flex items-center gap-2"
              >
                <span
                  :class="[
                    'flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold',
                    stepDot[s.state],
                  ]"
                >
                  <Check v-if="s.state === 'done'" class="h-3.5 w-3.5" />
                  <template v-else>{{ s.index }}</template>
                </span>
                <span
                  :class="[
                    'text-xs',
                    s.state === 'current'
                      ? 'font-medium text-amber-600 dark:text-amber-400'
                      : 'text-zinc-500',
                  ]"
                >
                  {{ t(`reports.approvals.state.${s.state}`) }}
                </span>
              </li>
            </ol>
          </div>

          <!-- Decision block -->
          <div class="px-6 py-5">
            <div v-if="canAct" data-test="decision-block">
              <label
                for="decision-note"
                class="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-500"
              >
                {{ t('reports.approvals.note') }}
              </label>
              <textarea
                id="decision-note"
                v-model="note"
                data-test="decision-note"
                rows="3"
                :placeholder="t('reports.approvals.notePlaceholder')"
                class="w-full rounded-lg border border-zinc-200 bg-transparent px-3 py-2 text-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/20 dark:border-zinc-700"
              />
              <p v-if="decisionError" class="mt-2 text-sm text-red-600 dark:text-red-400">
                {{ decisionError }}
              </p>
              <div class="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  data-test="approve-btn"
                  :disabled="acting"
                  class="inline-flex h-9 items-center gap-1.5 rounded-md bg-emerald-500 px-4 text-sm font-medium text-white transition hover:bg-emerald-400 disabled:opacity-50"
                  @click="decide('approve')"
                >
                  <ShieldCheck class="h-4 w-4" />
                  {{ t('reports.approvals.approve') }}
                </button>
                <button
                  type="button"
                  data-test="reject-btn"
                  :disabled="acting || !note.trim()"
                  class="inline-flex h-9 items-center gap-1.5 rounded-md border border-red-300 px-4 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-40 dark:border-red-500/40 dark:text-red-400 dark:hover:bg-red-500/10"
                  @click="decide('reject')"
                >
                  <X class="h-4 w-4" />
                  {{ t('reports.approvals.reject') }}
                </button>
              </div>
            </div>
            <p v-else data-test="not-approver" class="text-sm text-zinc-500">
              {{ t('reports.approvals.notApprover') }}
            </p>
          </div>
        </div>
      </section>
    </div>
  </AppShell>
</template>
