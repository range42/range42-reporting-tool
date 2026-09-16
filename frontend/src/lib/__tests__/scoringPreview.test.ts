import { describe, expect, it } from 'vitest'
import { rubricRollupPreview, scoringPreview, type PreviewSection } from '@/lib/scoringPreview'
import type { RubricCriterion } from '@/services/templates'

function section(over: Partial<PreviewSection> = {}): PreviewSection {
  return {
    grade_mode: 'numeric',
    grade: null,
    grade_min: 0,
    grade_max: 10,
    grade_weight: 1,
    ...over,
  }
}

describe('scoringPreview (preview only — rollup.py is canonical)', () => {
  it('weights section grades by grade_weight', () => {
    // (8·1 + 5·3) / 4 = 5.75
    expect(
      scoringPreview([
        section({ grade: 8, grade_weight: 1 }),
        section({ grade: 5, grade_weight: 3 }),
      ]),
    ).toBe(5.75)
  })

  it('excludes not_graded sections from numerator and denominator', () => {
    // The not_graded section carries a heavy weight; ignoring it entirely leaves 8.
    expect(
      scoringPreview([
        section({ grade: 8, grade_weight: 1 }),
        section({ grade_mode: 'not_graded', grade: null, grade_weight: 9 }),
      ]),
    ).toBe(8)
  })

  it('scales a pass_fail section to grade_max', () => {
    // A pass is worth grade_max (10), a fail grade_min (0).
    expect(scoringPreview([section({ grade_mode: 'pass_fail', grade: 1 })])).toBe(10)
    expect(scoringPreview([section({ grade_mode: 'pass_fail', grade: 0 })])).toBe(0)
    // No declared bounds: scales onto [0, 1], so a pass counts as 1.
    expect(
      scoringPreview([
        section({ grade_mode: 'pass_fail', grade: 1, grade_min: null, grade_max: null }),
      ]),
    ).toBe(1)
  })

  it('returns null while any gradable section is ungraded', () => {
    expect(scoringPreview([section({ grade: 8 }), section({ grade: null })])).toBeNull()
    expect(scoringPreview([])).toBeNull()
  })
})

describe('rubricRollupPreview (mirrors compute_rubric_rollup)', () => {
  const criteria: RubricCriterion[] = [
    { name: 'clarity', weight: 1, max_score: 5 },
    { name: 'evidence', weight: 3, max_score: 10 },
  ]

  it('weights each criterion by weight, not by max_score', () => {
    // (5/5·1 + 5/10·3) / 4 = 0.625 -> 0 + 0.625·10 = 6.25
    expect(
      rubricRollupPreview(
        criteria,
        [
          { criterion: 'clarity', score: 5, note: null },
          { criterion: 'evidence', score: 5, note: null },
        ],
        0,
        10,
      ),
    ).toBe(6.25)
  })

  it('clamps a score above its criterion maximum and ignores a stale criterion name', () => {
    expect(
      rubricRollupPreview(
        criteria,
        [
          { criterion: 'clarity', score: 99, note: null },
          { criterion: 'removed-by-a-template-edit', score: 1, note: null },
        ],
        0,
        10,
      ),
    ).toBe(10)
  })

  it('returns null when nothing can be computed', () => {
    expect(rubricRollupPreview(null, [], 0, 10)).toBeNull()
    expect(rubricRollupPreview(criteria, null, 0, 10)).toBeNull()
    expect(
      rubricRollupPreview(criteria, [{ criterion: 'nope', score: 1, note: null }], 0, 10),
    ).toBeNull()
  })

  it('scales onto 0..1 when the section declares no bounds', () => {
    expect(
      rubricRollupPreview(
        [{ name: 'clarity', weight: 1, max_score: 4 }],
        [{ criterion: 'clarity', score: 2, note: null }],
        null,
        null,
      ),
    ).toBe(0.5)
  })
})
