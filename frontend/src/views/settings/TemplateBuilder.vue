<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  TriangleAlert,
  Save,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Download,
  Copy,
  Archive,
  GripVertical,
  CheckCircle2,
  Circle,
} from '@lucide/vue'
import { VueDraggable } from 'vue-draggable-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import {
  getTemplate,
  updateTemplate,
  addSection,
  updateSection,
  deleteSection,
  deleteTemplate,
  publishTemplate,
  listVersions,
  reorderSections,
  exportTemplate,
  cloneTemplate,
  archiveTemplate,
  type TemplateDetail,
  type Section,
  type SectionInput,
  type ChoiceValue,
  type RubricCriterion,
  type TemplateVersion,
} from '@/services/templates'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const id = route.params.id as string
const token = computed(() => auth.token ?? '')

const tpl = ref<TemplateDetail | null>(null)
const versions = ref<TemplateVersion[]>([])
const error = ref('')
const saving = ref(false)

const readonly = computed(() => tpl.value?.status !== 'draft')

// Local editable metadata fields
const metaName = ref('')
const metaReportType = ref('')
const metaDescription = ref<string | null>(null)

onMounted(async () => {
  if (!auth.token) return
  try {
    const data = await getTemplate(token.value, id)
    tpl.value = data
    metaName.value = data.name
    metaReportType.value = data.report_type
    metaDescription.value = data.description
    versions.value = await listVersions(token.value, id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to load template'
  }
})

// Composition summary helpers
const richTextSections = computed(
  () => tpl.value?.sections.filter((s) => s.field_type === 'rich_text') ?? [],
)
const choiceSections = computed(
  () => tpl.value?.sections.filter((s) => s.field_type === 'choice') ?? [],
)
const totalCharBudget = computed(() =>
  richTextSections.value.reduce((acc, s) => acc + (s.char_limit ?? 0), 0),
)
const totalChoiceValues = computed(() =>
  choiceSections.value.reduce((acc, s) => acc + (s.choice_config?.values.length ?? 0), 0),
)

function defaultSection(): SectionInput {
  return {
    name: 'New section',
    field_type: 'rich_text',
    is_required: true,
    grade_mode: 'not_graded',
    grade_weight: 1,
    char_limit: null,
    grade_min: null,
    grade_max: null,
    rubric_criteria: null,
    evaluation_criteria: null,
    choice_config: null,
    mitre_attack_tags: [],
    capec_tags: [],
    cwe_tags: [],
    description: null,
  }
}

async function saveMeta(): Promise<void> {
  if (!tpl.value) return
  saving.value = true
  error.value = ''
  try {
    await updateTemplate(token.value, id, {
      name: metaName.value,
      report_type: metaReportType.value,
      description: metaDescription.value,
    })
    tpl.value.name = metaName.value
    tpl.value.report_type = metaReportType.value
    tpl.value.description = metaDescription.value
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Save failed'
  } finally {
    saving.value = false
  }
}

async function addSectionRow(): Promise<void> {
  if (!tpl.value) return
  error.value = ''
  try {
    const section = await addSection(token.value, id, defaultSection())
    tpl.value.sections.push(section)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to add section'
  }
}

async function patchSection(s: Section, partial: Partial<SectionInput>): Promise<void> {
  if (!tpl.value) return
  error.value = ''
  try {
    const updated = await updateSection(token.value, id, s.id, partial)
    const idx = tpl.value.sections.findIndex((x) => x.id === s.id)
    if (idx !== -1) tpl.value.sections[idx] = updated
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to update section'
  }
}

async function removeSection(s: Section): Promise<void> {
  if (!window.confirm(t('templates.deleteSectionConfirm'))) return
  if (!tpl.value) return
  error.value = ''
  try {
    await deleteSection(token.value, id, s.id)
    const idx = tpl.value.sections.findIndex((x) => x.id === s.id)
    if (idx !== -1) tpl.value.sections.splice(idx, 1)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to delete section'
  }
}

async function publish(): Promise<void> {
  error.value = ''
  try {
    await publishTemplate(token.value, id)
    tpl.value = await getTemplate(token.value, id)
    versions.value = await listVersions(token.value, id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to publish'
  }
}

// Drag-reorder + up/down

async function moveUp(s: Section): Promise<void> {
  if (!tpl.value) return
  const idx = tpl.value.sections.findIndex((x) => x.id === s.id)
  if (idx <= 0) return
  const sections = [...tpl.value.sections]
  const tmp = sections[idx - 1] as Section
  sections[idx - 1] = sections[idx] as Section
  sections[idx] = tmp
  tpl.value.sections = sections
  try {
    const ordered = await reorderSections(
      token.value,
      id,
      sections.map((x) => x.id),
    )
    if (tpl.value) tpl.value.sections = ordered
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to reorder'
  }
}

async function moveDown(s: Section): Promise<void> {
  if (!tpl.value) return
  const idx = tpl.value.sections.findIndex((x) => x.id === s.id)
  if (idx === -1 || idx >= tpl.value.sections.length - 1) return
  const sections = [...tpl.value.sections]
  const tmp = sections[idx + 1] as Section
  sections[idx + 1] = sections[idx] as Section
  sections[idx] = tmp
  tpl.value.sections = sections
  try {
    const ordered = await reorderSections(
      token.value,
      id,
      sections.map((x) => x.id),
    )
    if (tpl.value) tpl.value.sections = ordered
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to reorder'
  }
}

async function onDragEnd(): Promise<void> {
  if (!tpl.value) return
  const ids = tpl.value.sections.map((x) => x.id)
  try {
    const ordered = await reorderSections(token.value, id, ids)
    if (tpl.value) tpl.value.sections = ordered
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to reorder'
  }
}

// Field-type change — initialise choice_config when switching to 'choice'

async function onFieldTypeChange(s: Section, ft: string): Promise<void> {
  const patch: Partial<SectionInput> = { field_type: ft as 'rich_text' | 'choice' }
  if (ft === 'choice' && !s.choice_config) {
    patch.choice_config = { selection: 'single', values: [] }
  }
  await patchSection(s, patch)
}

// Choice-value editor

async function addChoiceValue(s: Section): Promise<void> {
  const config = s.choice_config ?? { selection: 'single' as const, values: [] }
  const newValues: ChoiceValue[] = [
    ...config.values,
    { code: '', label: '', position: config.values.length, deprecated_at: null },
  ]
  await patchSection(s, { choice_config: { ...config, values: newValues } })
}

async function removeChoiceValue(s: Section, idx: number): Promise<void> {
  if (!s.choice_config) return
  const newValues = s.choice_config.values.filter((_, i) => i !== idx)
  await patchSection(s, { choice_config: { ...s.choice_config, values: newValues } })
}

async function updateChoiceValue(
  s: Section,
  idx: number,
  partial: Partial<ChoiceValue>,
): Promise<void> {
  if (!s.choice_config) return
  const newValues = s.choice_config.values.map((v, i) => (i === idx ? { ...v, ...partial } : v))
  await patchSection(s, { choice_config: { ...s.choice_config, values: newValues } })
}

// Rubric editor

async function addRubricCriterion(s: Section): Promise<void> {
  const criteria: RubricCriterion[] = [
    ...(s.rubric_criteria ?? []),
    { name: '', weight: 1, max_score: 10 },
  ]
  await patchSection(s, { rubric_criteria: criteria })
}

async function removeRubricCriterion(s: Section, idx: number): Promise<void> {
  if (!s.rubric_criteria) return
  const criteria = s.rubric_criteria.filter((_, i) => i !== idx)
  await patchSection(s, { rubric_criteria: criteria })
}

// Header actions

async function doExport(): Promise<void> {
  try {
    const bundle = await exportTemplate(token.value, id)
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${tpl.value?.name ?? 'template'}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Export failed'
  }
}

async function doClone(): Promise<void> {
  try {
    const clone = await cloneTemplate(token.value, id)
    await router.push(`/settings/templates/${clone.id}`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Clone failed'
  }
}

async function doArchive(): Promise<void> {
  if (!window.confirm(t('templates.archive') + '?')) return
  try {
    await archiveTemplate(token.value, id)
    tpl.value = await getTemplate(token.value, id)
    versions.value = await listVersions(token.value, id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Archive failed'
  }
}

async function doDelete(): Promise<void> {
  if (!window.confirm(t('templates.deleteConfirm'))) return
  error.value = ''
  try {
    await deleteTemplate(token.value, id)
    await router.push('/settings/templates')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Delete failed'
  }
}

const inputClass =
  'h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900'
</script>

<template>
  <AppShell :title="tpl?.name ?? t('templates.title')">
    <template #actions>
      <RouterLink
        to="/settings/templates"
        class="flex h-9 items-center rounded-md px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
      >
        {{ t('templates.back') }}
      </RouterLink>
      <!-- Export: always available -->
      <button
        type="button"
        data-test="export"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-200 px-3 text-sm transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
        @click="doExport"
      >
        <Download class="h-4 w-4" />
        {{ t('templates.export') }}
      </button>
      <!-- Archive: published only -->
      <button
        v-if="tpl?.status === 'published'"
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-200 px-3 text-sm transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
        @click="doArchive"
      >
        <Archive class="h-4 w-4" />
        {{ t('templates.archive') }}
      </button>
      <!-- Delete: draft only -->
      <button
        v-if="!readonly"
        type="button"
        data-test="delete-template"
        class="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-red-500 transition hover:bg-red-500/10"
        @click="doDelete"
      >
        <Trash2 class="h-4 w-4" />
        {{ t('templates.delete') }}
      </button>
      <!-- Publish: draft only -->
      <button
        v-if="!readonly"
        type="button"
        data-test="publish"
        class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400"
        @click="publish"
      >
        {{ t('templates.publish') }}
      </button>
      <!-- Clone to edit: non-draft (shown when readonly) -->
      <button
        v-if="readonly"
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-200 px-3 text-sm transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
        @click="doClone"
      >
        <Copy class="h-4 w-4" />
        {{ t('templates.cloneToEdit') }}
      </button>
    </template>

    <!-- Error alert -->
    <div
      v-if="error"
      class="alert-error mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div v-if="tpl" class="flex gap-6">
      <!-- Main column -->
      <div class="min-w-0 flex-1 space-y-6">
        <!-- Metadata card -->
        <div
          class="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
        >
          <div class="border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
            <h2 class="text-sm font-semibold">{{ t('templates.name') }}</h2>
          </div>
          <div class="space-y-4 p-5">
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{ t('templates.name') }}</label>
              <input
                v-model="metaName"
                data-test="template-name"
                :disabled="readonly"
                :class="inputClass"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{
                t('templates.reportType')
              }}</label>
              <select v-model="metaReportType" :disabled="readonly" :class="inputClass">
                <option value="spot">Spot</option>
                <option value="custom">Custom</option>
                <option value="exercise">Exercise</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{
                t('templates.description')
              }}</label>
              <textarea
                v-model="metaDescription"
                :disabled="readonly"
                rows="3"
                class="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
              ></textarea>
            </div>
            <div class="flex justify-end">
              <button
                v-if="!readonly"
                type="button"
                data-test="save-template"
                :disabled="saving"
                class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-60"
                @click="saveMeta"
              >
                <Save class="h-4 w-4" />
                {{ t('templates.save') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Sections card -->
        <div
          class="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
        >
          <div
            class="flex items-center justify-between border-b border-zinc-200 px-5 py-3 dark:border-zinc-800"
          >
            <h2 class="text-sm font-semibold">
              {{ t('templates.sections') }}
              <span class="ml-1 text-xs font-normal text-zinc-400">drag to reorder</span>
            </h2>
            <button
              v-if="!readonly"
              type="button"
              data-test="add-section"
              class="flex h-8 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-xs font-medium text-white transition hover:bg-indigo-400"
              @click="addSectionRow"
            >
              <Plus class="h-3.5 w-3.5" />
              {{ t('templates.addSection') }}
            </button>
          </div>

          <VueDraggable
            v-model="tpl.sections"
            :disabled="readonly"
            tag="ul"
            class="divide-y divide-zinc-100 dark:divide-zinc-800"
            @end="onDragEnd"
          >
            <li
              v-for="(section, idx) in tpl.sections"
              :key="section.id"
              :data-test="`section-row-${section.id}`"
              class="p-4"
            >
              <div class="flex items-start gap-3">
                <!-- Grip + index -->
                <div class="mt-2 flex shrink-0 flex-col items-center gap-1">
                  <GripVertical
                    class="h-4 w-4 cursor-grab text-zinc-300 dark:text-zinc-600"
                    :class="{ 'opacity-30': readonly }"
                  />
                  <span
                    class="flex h-5 w-5 items-center justify-center rounded bg-zinc-200 text-[10px] font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    {{ idx + 1 }}
                  </span>
                </div>

                <div class="min-w-0 flex-1 space-y-3">
                  <div class="flex flex-wrap items-center gap-3">
                    <!-- Section name -->
                    <div class="min-w-48 flex-1">
                      <label class="mb-1 block text-xs text-zinc-500">{{
                        t('templates.name')
                      }}</label>
                      <input
                        :value="section.name"
                        :data-test="`section-name-${section.id}`"
                        :disabled="readonly"
                        :class="inputClass"
                        @change="
                          patchSection(section, { name: ($event.target as HTMLInputElement).value })
                        "
                      />
                    </div>
                    <!-- Field type -->
                    <div class="w-40">
                      <label class="mb-1 block text-xs text-zinc-500">{{
                        t('templates.fieldType')
                      }}</label>
                      <select
                        :value="section.field_type"
                        :data-test="`section-field-type-${section.id}`"
                        :disabled="readonly"
                        :class="inputClass"
                        @change="
                          onFieldTypeChange(section, ($event.target as HTMLSelectElement).value)
                        "
                      >
                        <option value="rich_text">Rich text</option>
                        <option value="choice">Choice</option>
                      </select>
                    </div>
                    <!-- Char limit (rich_text only) -->
                    <div v-if="section.field_type === 'rich_text'" class="w-32">
                      <label class="mb-1 block text-xs text-zinc-500">{{
                        t('templates.charLimit')
                      }}</label>
                      <input
                        type="number"
                        :value="section.char_limit ?? ''"
                        :disabled="readonly"
                        :class="inputClass"
                        @change="
                          patchSection(section, {
                            char_limit: ($event.target as HTMLInputElement).value
                              ? Number(($event.target as HTMLInputElement).value)
                              : null,
                          })
                        "
                      />
                    </div>
                    <!-- Required toggle -->
                    <div class="flex items-center gap-2 pt-5">
                      <input
                        type="checkbox"
                        :id="`req-${section.id}`"
                        :checked="section.is_required"
                        :disabled="readonly"
                        class="h-4 w-4 rounded border-zinc-300 accent-indigo-500 dark:border-zinc-600"
                        @change="
                          patchSection(section, {
                            is_required: ($event.target as HTMLInputElement).checked,
                          })
                        "
                      />
                      <label :for="`req-${section.id}`" class="text-xs text-zinc-500">
                        {{ t('templates.required') }}
                      </label>
                    </div>
                  </div>

                  <!-- Grade mode row -->
                  <div class="flex flex-wrap items-start gap-3">
                    <div class="w-40">
                      <label class="mb-1 block text-xs text-zinc-500">{{
                        t('templates.gradeMode')
                      }}</label>
                      <select
                        :value="section.grade_mode"
                        :disabled="readonly"
                        :class="inputClass"
                        @change="
                          patchSection(section, {
                            grade_mode: ($event.target as HTMLSelectElement).value as
                              | 'numeric'
                              | 'pass_fail'
                              | 'rubric'
                              | 'not_graded',
                          })
                        "
                      >
                        <option value="not_graded">Not graded</option>
                        <option value="numeric">Numeric</option>
                        <option value="pass_fail">Pass / Fail</option>
                        <option value="rubric">Rubric</option>
                      </select>
                    </div>
                    <!-- Weight -->
                    <div class="w-24">
                      <label class="mb-1 block text-xs text-zinc-500">{{
                        t('templates.weight')
                      }}</label>
                      <input
                        type="number"
                        :value="section.grade_weight"
                        :disabled="readonly"
                        :class="inputClass"
                        @change="
                          patchSection(section, {
                            grade_weight: Number(($event.target as HTMLInputElement).value),
                          })
                        "
                      />
                    </div>
                    <!-- Up / Down buttons -->
                    <div class="flex items-end gap-1 pb-0.5 pt-5">
                      <button
                        type="button"
                        :data-test="`move-up-${section.id}`"
                        :disabled="readonly || idx === 0"
                        class="flex h-8 w-8 items-center justify-center rounded border border-zinc-200 text-zinc-500 transition hover:bg-zinc-100 disabled:opacity-30 dark:border-zinc-700 dark:hover:bg-zinc-800"
                        :title="`Move section up`"
                        @click="moveUp(section)"
                      >
                        <ChevronUp class="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        :data-test="`move-down-${section.id}`"
                        :disabled="readonly || idx === tpl.sections.length - 1"
                        class="flex h-8 w-8 items-center justify-center rounded border border-zinc-200 text-zinc-500 transition hover:bg-zinc-100 disabled:opacity-30 dark:border-zinc-700 dark:hover:bg-zinc-800"
                        :title="`Move section down`"
                        @click="moveDown(section)"
                      >
                        <ChevronDown class="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  <!-- Choice-value editor (field_type === 'choice') -->
                  <div
                    v-if="section.field_type === 'choice'"
                    class="rounded-md border border-zinc-200 p-3 dark:border-zinc-800"
                  >
                    <div class="mb-2 flex items-center justify-between">
                      <p class="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                        {{ t('templates.choiceValues') }}
                      </p>
                      <!-- Selection type -->
                      <select
                        v-if="section.choice_config"
                        :value="section.choice_config.selection"
                        :disabled="readonly"
                        class="h-7 rounded border border-zinc-200 bg-white px-2 text-xs outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
                        @change="
                          patchSection(section, {
                            choice_config: {
                              ...(section.choice_config ?? { selection: 'single', values: [] }),
                              selection: ($event.target as HTMLSelectElement).value as
                                | 'single'
                                | 'multiple',
                            },
                          })
                        "
                      >
                        <option value="single">Single</option>
                        <option value="multiple">Multiple</option>
                      </select>
                    </div>
                    <div
                      v-if="section.choice_config && section.choice_config.values.length > 0"
                      class="mb-2 divide-y divide-zinc-100 rounded border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-700"
                    >
                      <div
                        v-for="(val, vi) in section.choice_config.values"
                        :key="vi"
                        class="flex items-center gap-2 px-2 py-1.5"
                        :class="{ 'opacity-50': val.deprecated_at }"
                      >
                        <input
                          :value="val.code"
                          :disabled="readonly"
                          placeholder="code"
                          class="w-28 rounded border border-zinc-200 bg-white px-2 py-0.5 font-mono text-xs outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
                          @change="
                            updateChoiceValue(section, vi, {
                              code: ($event.target as HTMLInputElement).value,
                            })
                          "
                        />
                        <input
                          :value="val.label"
                          :disabled="readonly"
                          placeholder="label"
                          class="flex-1 rounded border border-zinc-200 bg-white px-2 py-0.5 text-xs outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
                          @change="
                            updateChoiceValue(section, vi, {
                              label: ($event.target as HTMLInputElement).value,
                            })
                          "
                        />
                        <!-- Deprecate toggle -->
                        <button
                          type="button"
                          :disabled="readonly"
                          class="text-[10px] text-zinc-400 transition hover:text-amber-500 disabled:opacity-40"
                          :class="{ 'text-amber-500': val.deprecated_at }"
                          :title="t('templates.deprecate')"
                          @click="
                            updateChoiceValue(section, vi, {
                              deprecated_at: val.deprecated_at ? null : new Date().toISOString(),
                            })
                          "
                        >
                          {{ t('templates.deprecate') }}
                        </button>
                        <button
                          type="button"
                          :disabled="readonly"
                          class="text-zinc-400 transition hover:text-red-500 disabled:opacity-40"
                          @click="removeChoiceValue(section, vi)"
                        >
                          <Trash2 class="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    <button
                      type="button"
                      :disabled="readonly"
                      class="flex h-7 items-center gap-1.5 rounded border border-dashed border-zinc-300 px-2 text-xs text-zinc-500 transition hover:border-indigo-400 hover:text-indigo-500 disabled:opacity-40 dark:border-zinc-700"
                      @click="addChoiceValue(section)"
                    >
                      <Plus class="h-3 w-3" />
                      {{ t('templates.addValue') }}
                    </button>
                  </div>

                  <!-- Rubric criteria editor (grade_mode === 'rubric') -->
                  <div
                    v-if="section.grade_mode === 'rubric'"
                    class="rounded-md border border-zinc-200 p-3 dark:border-zinc-800"
                  >
                    <p class="mb-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                      {{ t('templates.rubric') }}
                    </p>
                    <div
                      v-if="section.rubric_criteria && section.rubric_criteria.length > 0"
                      class="mb-2 space-y-2"
                    >
                      <div
                        v-for="(crit, ci) in section.rubric_criteria"
                        :key="ci"
                        class="flex items-center gap-2"
                      >
                        <input
                          :value="crit.name"
                          :disabled="readonly"
                          :placeholder="t('templates.name')"
                          class="flex-1 rounded border border-zinc-200 bg-white px-2 py-1 text-xs outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
                          @change="
                            patchSection(section, {
                              rubric_criteria: section.rubric_criteria!.map((c, i) =>
                                i === ci
                                  ? {
                                      ...c,
                                      name: ($event.target as HTMLInputElement).value,
                                    }
                                  : c,
                              ),
                            })
                          "
                        />
                        <input
                          type="number"
                          :value="crit.weight"
                          :disabled="readonly"
                          :placeholder="t('templates.weight')"
                          class="w-16 rounded border border-zinc-200 bg-white px-2 py-1 text-xs outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
                          @change="
                            patchSection(section, {
                              rubric_criteria: section.rubric_criteria!.map((c, i) =>
                                i === ci
                                  ? {
                                      ...c,
                                      weight: Number(($event.target as HTMLInputElement).value),
                                    }
                                  : c,
                              ),
                            })
                          "
                        />
                        <input
                          type="number"
                          :value="crit.max_score"
                          :disabled="readonly"
                          :placeholder="t('templates.maxScore')"
                          class="w-16 rounded border border-zinc-200 bg-white px-2 py-1 text-xs outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
                          @change="
                            patchSection(section, {
                              rubric_criteria: section.rubric_criteria!.map((c, i) =>
                                i === ci
                                  ? {
                                      ...c,
                                      max_score: Number(($event.target as HTMLInputElement).value),
                                    }
                                  : c,
                              ),
                            })
                          "
                        />
                        <button
                          type="button"
                          :disabled="readonly"
                          class="text-zinc-400 transition hover:text-red-500 disabled:opacity-40"
                          @click="removeRubricCriterion(section, ci)"
                        >
                          <Trash2 class="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    <button
                      type="button"
                      :disabled="readonly"
                      class="flex h-7 items-center gap-1.5 rounded border border-dashed border-zinc-300 px-2 text-xs text-zinc-500 transition hover:border-indigo-400 hover:text-indigo-500 disabled:opacity-40 dark:border-zinc-700"
                      @click="addRubricCriterion(section)"
                    >
                      <Plus class="h-3 w-3" />
                      {{ t('templates.addCriterion') }}
                    </button>
                  </div>

                  <!-- MITRE / CWE tags -->
                  <div class="flex flex-wrap gap-3">
                    <div class="min-w-40 flex-1">
                      <label class="mb-1 block text-xs text-zinc-500">MITRE ATT&amp;CK tags</label>
                      <input
                        :value="section.mitre_attack_tags.join(', ')"
                        :disabled="readonly"
                        :class="inputClass"
                        placeholder="e.g. T1059, T1078"
                        @change="
                          patchSection(section, {
                            mitre_attack_tags: ($event.target as HTMLInputElement).value
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        "
                      />
                    </div>
                    <div class="min-w-40 flex-1">
                      <label class="mb-1 block text-xs text-zinc-500">CWE tags</label>
                      <input
                        :value="section.cwe_tags.join(', ')"
                        :disabled="readonly"
                        :class="inputClass"
                        placeholder="e.g. CWE-79, CWE-89"
                        @change="
                          patchSection(section, {
                            cwe_tags: ($event.target as HTMLInputElement).value
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        "
                      />
                    </div>
                  </div>
                </div>

                <!-- Delete button -->
                <button
                  v-if="!readonly"
                  type="button"
                  :data-test="`delete-section-${section.id}`"
                  class="mt-6 rounded-md p-1.5 text-red-400 transition hover:bg-red-500/10 hover:text-red-500"
                  @click="removeSection(section)"
                >
                  <Trash2 class="h-4 w-4" />
                </button>
              </div>
            </li>
          </VueDraggable>

          <div
            v-if="tpl.sections.length === 0"
            class="px-5 py-10 text-center text-sm text-zinc-400"
          >
            {{ t('templates.addSection') }}
          </div>
        </div>
      </div>

      <!-- Right column: composition summary + live preview + version history -->
      <aside class="hidden w-72 shrink-0 space-y-4 xl:block">
        <!-- Section composition -->
        <div
          class="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <p class="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            {{ t('templates.composition') }}
          </p>
          <div class="space-y-2.5 text-xs">
            <div class="flex justify-between">
              <span class="text-zinc-500">Rich text sections</span>
              <span class="font-mono">{{ richTextSections.length }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-zinc-500">Choice sections</span>
              <span class="font-mono">{{ choiceSections.length }}</span>
            </div>
            <div class="flex justify-between border-t border-zinc-100 pt-2 dark:border-zinc-800">
              <span class="text-zinc-500">Total char budget</span>
              <span class="font-mono">{{ totalCharBudget.toLocaleString() }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-zinc-500">Choice values defined</span>
              <span class="font-mono">{{ totalChoiceValues }}</span>
            </div>
          </div>
        </div>

        <!-- Live preview -->
        <div
          class="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <p class="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            {{ t('templates.preview') }}
          </p>
          <div class="space-y-3">
            <div v-for="section in tpl.sections" :key="`prev-${section.id}`">
              <p class="mb-0.5 text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
                {{ section.name }}
                <span v-if="section.is_required" class="text-red-400">*</span>
              </p>
              <p v-if="section.description" class="mb-1 text-[10px] text-zinc-400">
                {{ section.description }}
              </p>
              <!-- rich_text preview -->
              <textarea
                v-if="section.field_type === 'rich_text'"
                disabled
                rows="2"
                :placeholder="
                  section.char_limit ? `Max ${section.char_limit} characters` : 'Write here…'
                "
                class="w-full resize-none rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs opacity-60 dark:border-zinc-700 dark:bg-zinc-800"
              ></textarea>
              <!-- choice preview -->
              <template v-else-if="section.field_type === 'choice'">
                <select
                  v-if="section.choice_config?.selection === 'single'"
                  disabled
                  class="w-full rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs opacity-60 dark:border-zinc-700 dark:bg-zinc-800"
                >
                  <option
                    v-for="val in section.choice_config?.values ?? []"
                    :key="val.code"
                    :value="val.code"
                  >
                    {{ val.label || val.code }}
                  </option>
                </select>
                <div v-else class="space-y-1">
                  <label
                    v-for="val in section.choice_config?.values ?? []"
                    :key="val.code"
                    class="flex items-center gap-2 text-xs opacity-60"
                  >
                    <input type="checkbox" disabled class="h-3 w-3" />
                    {{ val.label || val.code }}
                  </label>
                </div>
              </template>
            </div>
            <p v-if="tpl.sections.length === 0" class="text-xs text-zinc-400">No sections yet.</p>
          </div>
        </div>

        <!-- Version history -->
        <div
          class="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <p class="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            {{ t('templates.versions') }}
          </p>
          <ul class="space-y-1.5 text-xs">
            <li v-for="v in versions" :key="v.id" class="flex items-center gap-2">
              <component
                :is="v.status === 'published' ? CheckCircle2 : Circle"
                class="h-3.5 w-3.5 shrink-0"
                :class="v.status === 'published' ? 'text-emerald-500' : 'text-zinc-400'"
              />
              <RouterLink
                :to="`/settings/templates/${v.id}`"
                class="text-zinc-600 hover:text-indigo-500 dark:text-zinc-400"
              >
                v{{ v.version }}
                <span class="text-zinc-400">· {{ v.status }}</span>
              </RouterLink>
            </li>
            <li v-if="versions.length === 0" class="text-zinc-400">No versions yet.</li>
          </ul>
        </div>
      </aside>
    </div>
  </AppShell>
</template>
