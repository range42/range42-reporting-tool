import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ApiError } from '@/services/http'
import {
  getEvaluation,
  putGrade,
  type EvaluationDetail,
  type GradableSection,
  type GradeUpsertInput,
} from '@/services/evaluations'
import { parseGrade } from '@/lib/decimal'
import { scoringPreview, type PreviewSection } from '@/lib/scoringPreview'

/** Where a section's grade currently stands, wherever the value came from. */
interface Draft {
  readonly input: GradeUpsertInput
  readonly grade: number | null
}

interface LoadContext {
  readonly token: string
  readonly exerciseId: string
  readonly rid: string
  readonly evid: string
}

const OUT_OF_RANGE = 'out_of_range'
const UNKNOWN_SAVE_ERROR = 'save_failed'

export const useEvaluationStore = defineStore('evaluation', () => {
  const ctx = ref<LoadContext | null>(null)
  const detail = ref<EvaluationDetail | null>(null)
  /** Section-keyed so a grade control can find its own row without scanning the list. */
  const sectionsById = ref<Record<string, GradableSection>>({})
  const order = ref<string[]>([])
  const drafts = ref<Record<string, Draft>>({})
  const errors = ref<Record<string, string>>({})
  const saving = ref(false)
  /** Set when the published grade moved under us; a flush would overwrite someone's work. */
  const needsReload = ref(false)
  const gradeVersion = ref<number | null>(null)
  const serverOverallGrade = ref<number | null>(null)
  const serverGradedCount = ref<number | null>(null)

  let pending: ReturnType<typeof setTimeout> | null = null

  const sections = computed<GradableSection[]>(() =>
    order.value.map((id) => sectionsById.value[id]!),
  )
  const gradableSections = computed(() =>
    sections.value.filter((s) => s.grade_mode !== 'not_graded'),
  )
  const gradableCount = computed(() => gradableSections.value.length)

  /** The stored grade, or the draft that supersedes it. Drafts win: they are what the user sees. */
  function effectiveGrade(sectionId: string): number | null {
    const draft = drafts.value[sectionId]
    if (draft) return draft.grade
    return parseGrade(sectionsById.value[sectionId]?.grade?.grade ?? null)
  }

  const isDirty = (sectionId: string): boolean => sectionId in drafts.value
  const errorFor = (sectionId: string): string | null => errors.value[sectionId] ?? null
  const dirtySectionIds = computed(() => Object.keys(drafts.value))

  const localGradedCount = computed(
    () => gradableSections.value.filter((s) => effectiveGrade(s.report_section_id) !== null).length,
  )
  /** The server's count wins once it has answered for everything on screen — a peer's save
   *  can move it. While a draft is unsaved the local count is what the user is looking at,
   *  and a server count that predates the edit would read as the edit being lost. */
  const gradedCount = computed(() =>
    dirtySectionIds.value.length > 0 || serverGradedCount.value === null
      ? localGradedCount.value
      : serverGradedCount.value,
  )

  const previewSections = computed<PreviewSection[]>(() =>
    sections.value.map((s) => ({
      grade_mode: s.grade_mode,
      grade: effectiveGrade(s.report_section_id),
      grade_min: parseGrade(s.grade_min),
      grade_max: parseGrade(s.grade_max),
      grade_weight: parseGrade(s.grade_weight) ?? 1,
    })),
  )
  /** Provisional only — `rollup.py` is canonical (D6). */
  const previewGrade = computed(() => scoringPreview(previewSections.value))
  /** The server's number if it has one, else the local preview. */
  const overallGrade = computed(() => serverOverallGrade.value ?? previewGrade.value)

  const canFinalize = computed(
    () =>
      gradableCount.value > 0 &&
      Object.keys(errors.value).length === 0 &&
      gradableSections.value.every((s) => effectiveGrade(s.report_section_id) !== null),
  )

  function adopt(d: EvaluationDetail): void {
    detail.value = d
    sectionsById.value = Object.fromEntries(d.sections.map((s) => [s.report_section_id, s]))
    order.value = d.sections.map((s) => s.report_section_id)
    gradeVersion.value = d.grade_version
    serverOverallGrade.value = parseGrade(d.overall_grade)
    serverGradedCount.value = d.graded_section_count
  }

  async function load(token: string, exerciseId: string, rid: string, evid: string): Promise<void> {
    ctx.value = { token, exerciseId, rid, evid }
    drafts.value = {}
    errors.value = {}
    needsReload.value = false
    adopt(await getEvaluation(token, exerciseId, rid, evid))
  }

  /** Numeric grades must sit inside the template's declared range; the server refuses
   *  otherwise, so catching it here saves a round trip and keeps the draft editable. */
  function rangeError(section: GradableSection, input: GradeUpsertInput): string | null {
    if (section.grade_mode !== 'numeric' || typeof input.grade !== 'number') return null
    const min = parseGrade(section.grade_min)
    const max = parseGrade(section.grade_max)
    if (min !== null && input.grade < min) return OUT_OF_RANGE
    if (max !== null && input.grade > max) return OUT_OF_RANGE
    return null
  }

  /** Record an edit. Immutable throughout: the stored grade row is never touched, and each
   *  call replaces the draft and error maps rather than mutating them in place. */
  function setGrade(sectionId: string, input: GradeUpsertInput): void {
    const section = sectionsById.value[sectionId]
    if (!section) return

    const invalid = rangeError(section, input)
    if (invalid) {
      // Rejected: no draft, so a bad value is never queued for a save.
      errors.value = { ...errors.value, [sectionId]: invalid }
      return
    }
    errors.value = Object.fromEntries(
      Object.entries(errors.value).filter(([id]) => id !== sectionId),
    )
    drafts.value = {
      ...drafts.value,
      [sectionId]: { input, grade: input.grade ?? null },
    }
  }

  /** A newer published version means our drafts are against a dead grade (D19). */
  function observeGradeVersion(version: number): void {
    if (gradeVersion.value !== null && version > gradeVersion.value) needsReload.value = true
  }

  function saveErrorCode(e: unknown): string {
    return e instanceof ApiError ? e.code : UNKNOWN_SAVE_ERROR
  }

  /** PUT every dirty section, then re-read the detail for the server's own numbers.
   *  A failed section keeps its draft so the edit is not silently lost. */
  async function flush(): Promise<void> {
    if (pending !== null) {
      clearTimeout(pending)
      pending = null
    }
    const context = ctx.value
    if (!context || needsReload.value || saving.value) return
    const ids = dirtySectionIds.value
    if (ids.length === 0) return

    saving.value = true
    const failed: Record<string, string> = {}
    const saved: string[] = []
    try {
      for (const id of ids) {
        const draft = drafts.value[id]
        if (!draft) continue
        try {
          await putGrade(
            context.token,
            context.exerciseId,
            context.rid,
            context.evid,
            id,
            draft.input,
          )
          saved.push(id)
        } catch (e: unknown) {
          failed[id] = saveErrorCode(e)
        }
      }
      drafts.value = Object.fromEntries(
        Object.entries(drafts.value).filter(([id]) => !saved.includes(id)),
      )
      if (Object.keys(failed).length > 0) errors.value = { ...errors.value, ...failed }
      // The server is the only authority on overall_grade, graded_section_count and
      // grade_version — the PUT response carries the section row alone.
      if (saved.length > 0) {
        try {
          adopt(await getEvaluation(context.token, context.exerciseId, context.rid, context.evid))
        } catch {
          // The writes landed; a failed refresh leaves the local preview standing.
        }
      }
    } finally {
      saving.value = false
    }
  }

  /** Debounce lives here so component tests can call `flush()` directly instead of
   *  faking timers. Each call supersedes the previous pending flush. */
  function flushAfter(ms: number): void {
    if (pending !== null) clearTimeout(pending)
    pending = setTimeout(() => {
      pending = null
      void flush()
    }, ms)
  }

  function reset(): void {
    ctx.value = null
    detail.value = null
    sectionsById.value = {}
    order.value = []
    drafts.value = {}
    errors.value = {}
    needsReload.value = false
    gradeVersion.value = null
    serverOverallGrade.value = null
    serverGradedCount.value = null
  }

  return {
    detail,
    sectionsById,
    sections,
    saving,
    needsReload,
    gradeVersion,
    gradableCount,
    gradedCount,
    previewGrade,
    overallGrade,
    canFinalize,
    dirtySectionIds,
    effectiveGrade,
    isDirty,
    errorFor,
    load,
    setGrade,
    observeGradeVersion,
    flush,
    flushAfter,
    reset,
  }
})
