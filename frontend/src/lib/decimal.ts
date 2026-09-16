/**
 * Two-decimal grade parsing and formatting.
 *
 * The backend pins every grade to one wire form — `NUMERIC(5,2)` serialized as a
 * two-decimal STRING — so the UI must never hand a raw float to the API or read one
 * back as a float and re-serialize it differently. These two helpers are the only
 * crossing points between the wire string and the number the inputs bind to.
 */

/** Wire form: digits with at most two decimal places. Grades are non-negative (DB CHECK). */
const TWO_DECIMAL = /^\d+(\.\d{1,2})?$/

const CENTS = 100

/** Wire string -> number. Returns null for absent, blank or non-two-decimal input. */
export function parseGrade(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined) return null
  const trimmed = raw.trim()
  if (trimmed === '' || !TWO_DECIMAL.test(trimmed)) return null
  return Math.round(Number(trimmed) * CENTS) / CENTS
}

/** Number -> wire string, always two decimals. Returns null so a cleared grade stays null. */
export function formatGrade(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  return (Math.round(value * CENTS) / CENTS).toFixed(2)
}
