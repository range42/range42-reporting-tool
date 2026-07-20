<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { TriangleAlert, Check, RotateCcw } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import {
  getReport,
  saveSection,
  submitReport,
  type ReportDetail,
  type ReportSection,
  type SectionAnswerBody,
} from '@/services/reports'
import { useDraftCache } from '@/composables/useDraftCache'
import { useCharBudget } from '@/composables/useCharBudget'
import RichTextField from '@/views/reports/RichTextField.vue'
import SectionConflictMerge from '@/views/reports/SectionConflictMerge.vue'

const AUTOSAVE_MS = 30_000

interface ChoiceOption {
  code: string
  label: string
}

interface EditableSection {
  id: string
  sectionDefId: string
  fieldType: 'rich_text' | 'choice'
  name: string
  description: string | null
  charLimit: number | null
  isRequired: boolean
  selection: 'single' | 'multiple'
  options: ChoiceOption[]
  content: string
  choice: string[]
  version: number
  serverUpdatedAt: string
  // Last state known to be in sync with the server — the "base" of a 3-way merge.
  baseContent: string
  baseChoice: string[]
  baseVersion: number
  // Server section carried by a stale-version 409; non-null renders the merge panel.
  conflictServer: ReportSection | null
  restore: boolean
  savedLabel: string
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
// router is used by template-independent navigation in a later slice; keep a
// reference so the wiring is in place without an unused-var lint error.
void router

const exerciseId = route.params.exerciseId as string
const rid = route.params.rid as string
const token = computed(() => auth.token ?? '')
const draft = useDraftCache(rid)

const report = ref<ReportDetail | null>(null)
const sections = reactive<EditableSection[]>([])
const error = ref('')
const submitError = ref('')

const readOnly = computed(() => report.value !== null && report.value.status !== 'draft')

const autosaveTimers: Record<string, ReturnType<typeof setTimeout>> = {}

function toEditable(s: ReportDetail['sections'][number]): EditableSection {
  return {
    id: s.id,
    sectionDefId: s.section_def_id,
    fieldType: s.field_type,
    name: s.name,
    description: s.description,
    charLimit: s.char_limit,
    isRequired: s.is_required,
    selection: s.choice_config?.selection ?? 'single',
    options: (s.choice_config?.values ?? []).map((v) => ({ code: v.code, label: v.label })),
    content: s.content ?? '',
    choice: s.choice_values ?? [],
    version: s.version,
    serverUpdatedAt: s.updated_at,
    baseContent: s.content ?? '',
    baseChoice: s.choice_values ?? [],
    baseVersion: s.version,
    conflictServer: null,
    restore: false,
    savedLabel: '',
  }
}

onMounted(async () => {
  if (!auth.token) return
  try {
    const detail = await getReport(token.value, exerciseId, rid)
    report.value = detail
    sections.splice(0, sections.length, ...detail.sections.map(toEditable))
    for (const s of sections) {
      if (draft.isNewerThanServer(s.sectionDefId, s.serverUpdatedAt)) s.restore = true
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.loadError')
  }
})

onBeforeUnmount(() => {
  for (const id of Object.keys(autosaveTimers)) clearTimeout(autosaveTimers[id])
})

const budget = useCharBudget()

function charCount(s: EditableSection): number {
  return budget.count(s.content)
}

function overLimit(s: EditableSection): boolean {
  return budget.overLimit(s.content, s.charLimit)
}

function bodyFor(s: EditableSection): SectionAnswerBody {
  return s.fieldType === 'rich_text'
    ? { kind: 'rich_text', content: s.content }
    : { kind: 'choice', choice_values: s.choice }
}

function statusOf(e: unknown): number | undefined {
  if (e instanceof ApiError) return e.status
  if (e && typeof e === 'object' && 'status' in e) {
    const s = (e as { status?: unknown }).status
    return typeof s === 'number' ? s : undefined
  }
  return undefined
}

/** Extract the current server section from a stale-version 409's `details[]`, if usable. */
function staleSectionOf(e: unknown): ReportSection | null {
  if (!e || typeof e !== 'object' || !('details' in e)) return null
  const details = (e as { details?: unknown }).details
  if (!Array.isArray(details)) return null
  for (const d of details) {
    if (!d || typeof d !== 'object') continue
    const entry = d as { error?: unknown; section?: unknown }
    if (entry.error !== 'stale_version') continue
    const section = entry.section
    if (
      section &&
      typeof section === 'object' &&
      typeof (section as ReportSection).version === 'number'
    ) {
      return section as ReportSection
    }
  }
  return null
}

function onEdited(s: EditableSection): void {
  draft.write(
    s.sectionDefId,
    s.fieldType === 'rich_text' ? s.content : s.choice,
    new Date().toISOString(),
  )
  if (autosaveTimers[s.id]) clearTimeout(autosaveTimers[s.id])
  autosaveTimers[s.id] = setTimeout(() => void save(s), AUTOSAVE_MS)
}

async function save(s: EditableSection): Promise<void> {
  if (readOnly.value || overLimit(s)) return
  if (autosaveTimers[s.id]) clearTimeout(autosaveTimers[s.id])
  try {
    const saved = await saveSection(token.value, exerciseId, rid, s.id, {
      version: s.version,
      body: bodyFor(s),
    })
    s.version = saved.version
    s.content = saved.content ?? ''
    s.choice = saved.choice_values ?? []
    s.baseContent = s.content
    s.baseChoice = [...s.choice]
    s.baseVersion = saved.version
    s.conflictServer = null
    s.savedLabel = t('reports.savedNow')
    draft.clear(s.sectionDefId)
  } catch (e) {
    if (statusOf(e) === 409) {
      const server = staleSectionOf(e)
      if (server) s.conflictServer = server
      else await reloadSection(s)
    } else {
      error.value = e instanceof ApiError ? e.message : t('reports.saveError')
    }
  }
}

function keepMine(s: EditableSection): void {
  if (!s.conflictServer) return
  s.version = s.conflictServer.version
  s.conflictServer = null
  void save(s)
}

function useServer(s: EditableSection): void {
  const server = s.conflictServer
  if (!server) return
  s.content = server.content ?? ''
  s.choice = server.choice_values ?? []
  s.version = server.version
  s.serverUpdatedAt = server.updated_at
  s.baseContent = s.content
  s.baseChoice = [...s.choice]
  s.baseVersion = server.version
  s.conflictServer = null
  draft.clear(s.sectionDefId)
}

function resolveManual(s: EditableSection, content: string): void {
  if (!s.conflictServer) return
  s.content = content
  s.version = s.conflictServer.version
  s.conflictServer = null
  void save(s)
}

async function reloadSection(s: EditableSection): Promise<void> {
  try {
    const detail = await getReport(token.value, exerciseId, rid)
    const fresh = detail.sections.find((x) => x.id === s.id)
    if (fresh) Object.assign(s, toEditable(fresh))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.loadError')
  }
}

function applyRestore(s: EditableSection): void {
  const entry = draft.read(s.sectionDefId)
  if (entry) {
    if (s.fieldType === 'rich_text') s.content = String(entry.value ?? '')
    else s.choice = Array.isArray(entry.value) ? (entry.value as string[]) : []
  }
  s.restore = false
}

function dismissRestore(s: EditableSection): void {
  draft.clear(s.sectionDefId)
  s.restore = false
}

function toggleChoice(s: EditableSection, code: string): void {
  if (s.selection === 'single') {
    s.choice = [code]
  } else {
    s.choice = s.choice.includes(code) ? s.choice.filter((c) => c !== code) : [...s.choice, code]
  }
  onEdited(s)
}

async function submit(): Promise<void> {
  submitError.value = ''
  try {
    const updated = await submitReport(token.value, exerciseId, rid)
    report.value = updated
  } catch (e) {
    if (statusOf(e) === 409) submitError.value = t('reports.submitBlocked')
    else submitError.value = e instanceof ApiError ? e.message : t('reports.submitError')
  }
}
</script>

<template>
  <AppShell :title="report?.name ?? t('reports.title')">
    <template #actions>
      <button
        v-if="report && !readOnly"
        type="button"
        data-test="submit-report"
        class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400"
        @click="submit"
      >
        <Check class="h-4 w-4" />
        {{ t('reports.submit') }}
      </button>
    </template>

    <div class="mx-auto max-w-3xl">
      <div class="mb-6 flex items-baseline justify-between">
        <h1 class="text-2xl font-semibold tracking-tight">{{ report?.name }}</h1>
        <span
          v-if="report"
          class="rounded px-1.5 py-0.5 text-[11px] font-medium"
          :class="
            report.status === 'submitted'
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300'
              : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
          "
        >
          {{ t(`reports.statusLabel.${report.status}`) }}
        </span>
      </div>

      <div
        v-if="error"
        class="mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
      >
        <TriangleAlert class="h-4 w-4 shrink-0" />
        <span>{{ error }}</span>
      </div>
      <div
        v-if="submitError"
        data-test="submit-error"
        class="mb-4 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
      >
        <TriangleAlert class="h-4 w-4 shrink-0" />
        <span>{{ submitError }}</span>
      </div>

      <div class="space-y-8">
        <section
          v-for="s in sections"
          :key="s.id"
          class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <div class="mb-2 flex items-center gap-2">
            <h2 class="font-medium">{{ s.name }}</h2>
            <span v-if="s.isRequired" class="text-xs text-red-500">*</span>
          </div>
          <p v-if="s.description" class="mb-3 text-sm text-zinc-500">{{ s.description }}</p>

          <div
            v-if="s.restore"
            :data-test="`restore-${s.id}`"
            class="mb-3 flex items-center justify-between gap-2 rounded-md border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-sm"
          >
            <span class="flex items-center gap-1.5 text-indigo-700 dark:text-indigo-300">
              <RotateCcw class="h-4 w-4" />
              {{ t('reports.restorePrompt') }}
            </span>
            <span class="flex gap-2">
              <button
                type="button"
                class="rounded border border-indigo-400 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:text-indigo-300"
                @click="applyRestore(s)"
              >
                {{ t('reports.restore') }}
              </button>
              <button
                type="button"
                class="rounded px-2 py-0.5 text-xs text-zinc-500"
                @click="dismissRestore(s)"
              >
                {{ t('reports.discard') }}
              </button>
            </span>
          </div>

          <SectionConflictMerge
            v-if="s.conflictServer"
            :test-id="s.id"
            :base="s.fieldType === 'rich_text' ? s.baseContent : s.baseChoice.join(', ')"
            :local="s.fieldType === 'rich_text' ? s.content : s.choice.join(', ')"
            :server="
              s.fieldType === 'rich_text'
                ? (s.conflictServer.content ?? '')
                : (s.conflictServer.choice_values ?? []).join(', ')
            "
            :server-version="s.conflictServer.version"
            :field-type="s.fieldType"
            @keep-mine="keepMine(s)"
            @use-server="useServer(s)"
            @resolved-manual="(content) => resolveManual(s, content)"
          />

          <template v-if="s.fieldType === 'rich_text'">
            <RichTextField
              v-model="s.content"
              :test-id="s.id"
              :disabled="readOnly"
              @update:model-value="onEdited(s)"
            />
            <div class="mt-2 flex items-center justify-between text-xs">
              <span
                v-if="s.charLimit !== null"
                :data-test="`char-counter-${s.id}`"
                :class="overLimit(s) ? 'font-medium text-red-500' : 'text-zinc-400'"
              >
                {{ charCount(s) }}/{{ s.charLimit }}
              </span>
              <span v-else :data-test="`char-counter-${s.id}`" class="text-zinc-400">
                {{ charCount(s) }}
              </span>
              <span class="text-zinc-400">{{ s.savedLabel }}</span>
            </div>
          </template>

          <template v-else>
            <div class="space-y-1.5">
              <label
                v-for="opt in s.options"
                :key="opt.code"
                class="flex items-center gap-2 text-sm"
              >
                <input
                  :type="s.selection === 'single' ? 'radio' : 'checkbox'"
                  :name="`choice-${s.id}`"
                  :value="opt.code"
                  :checked="s.choice.includes(opt.code)"
                  :disabled="readOnly"
                  @change="toggleChoice(s, opt.code)"
                />
                {{ opt.label }}
              </label>
            </div>
            <div class="mt-2 text-right text-xs text-zinc-400">{{ s.savedLabel }}</div>
          </template>

          <div v-if="!readOnly" class="mt-3 flex justify-end">
            <button
              type="button"
              :data-test="`save-${s.id}`"
              :disabled="overLimit(s)"
              class="flex h-8 items-center rounded-md border border-zinc-200 px-3 text-sm transition hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-800 dark:hover:bg-zinc-800"
              @click="save(s)"
            >
              {{ t('reports.save') }}
            </button>
          </div>
        </section>
      </div>
    </div>
  </AppShell>
</template>
