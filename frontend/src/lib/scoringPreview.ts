import type { GradeMode } from '@/services/evaluations'

/**
 * PREVIEW ONLY — `backend/app/services/scoring/rollup.py` is canonical (D6).
 *
 * This mirrors the server's §4.2 arithmetic so an evaluator sees their overall grade move
 * as they type, without a round trip per keystroke. It is NEVER the number of record: the
 * server recomputes on every save and the store adopts the response, discarding whatever
 * this produced. Two rules keep the two implementations honest about their disagreement:
 *
 *   - Anything this cannot compute returns null rather than a guess.
 *   - The moment a server value arrives it wins, unconditionally.
 *
 * A drift between this and `rollup.py` is a display bug, never a grading bug — but it is
 * still a bug: `rollup.py` is the file to read when changing either.
 */

const CENTS = 100

export interface PreviewSection {
  grade_mode: GradeMode
  /** Numeric grade, or 0/1 for pass_fail (scaled here, exactly as the server scales it). */
  grade: number | null
  grade_min: number | null
  grade_max: number | null
  grade_weight: number
}

/** The section's output range. A section declaring none has no scale to stretch onto, so
 *  a normalized 0..1 fraction is the honest answer — same default as `_resolve_bounds`. */
function bounds(s: PreviewSection): readonly [number, number] {
  return [s.grade_min ?? 0, s.grade_max ?? 1]
}

/** The scaled value this section contributes, or null when it contributes nothing.
 *  null means excluded from BOTH numerator and weight denominator — returning 0 would
 *  silently depress the average instead. */
function sectionValue(s: PreviewSection): number | null {
  if (s.grade_mode === 'not_graded' || s.grade === null) return null
  if (s.grade_mode === 'pass_fail') {
    const [low, high] = bounds(s)
    return low + s.grade * (high - low)
  }
  return s.grade
}

/**
 * Weighted mean of the graded sections, to two decimals — or null.
 *
 * Null while ANY gradable section is still ungraded: a partial average shown as the overall
 * grade reads as a finished number, and an evaluator part-way through their sections would
 * watch it swing on every save. `not_graded` sections never count, whatever their weight.
 */
export function scoringPreview(sections: readonly PreviewSection[]): number | null {
  const gradable = sections.filter((s) => s.grade_mode !== 'not_graded')
  if (gradable.length === 0) return null
  if (gradable.some((s) => s.grade === null)) return null

  let weighted = 0
  let weight = 0
  for (const s of gradable) {
    const value = sectionValue(s)
    if (value === null || s.grade_weight <= 0) continue
    weighted += value * s.grade_weight
    weight += s.grade_weight
  }
  if (weight === 0) return null
  // HALF_UP to the column's two places, matching `quantize_grade` (M11).
  return Math.round((weighted / weight) * CENTS) / CENTS
}
