import { useI18n } from 'vue-i18n'
import { parseGrade } from '@/lib/decimal'
import type { GradableSection } from '@/services/evaluations'

/** The one-line grading summary for a section: grade mode, range and weight. */
export function useSectionMeta(): { metaFor: (s: GradableSection) => string } {
  const { t } = useI18n()

  function metaFor(s: GradableSection): string {
    if (s.grade_mode === 'not_graded') return t('evaluations.modeNotGraded')
    const weight = t('evaluations.weight', { weight: parseGrade(s.grade_weight) ?? 1 })
    const mode =
      s.grade_mode === 'numeric'
        ? t('evaluations.modeNumeric', {
            min: parseGrade(s.grade_min) ?? 0,
            max: parseGrade(s.grade_max) ?? '—',
          })
        : t(s.grade_mode === 'pass_fail' ? 'evaluations.modePassFail' : 'evaluations.modeRubric')
    return `${mode} · ${weight}`
  }

  return { metaFor }
}
