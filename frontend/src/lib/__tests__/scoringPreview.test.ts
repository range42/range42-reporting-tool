import { describe, expect, it } from 'vitest'
import { scoringPreview, type PreviewSection } from '@/lib/scoringPreview'

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

describe('scoringPreview (preview only — rollup.py is canonical, D6)', () => {
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
