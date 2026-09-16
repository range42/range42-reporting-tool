import { describe, expect, it } from 'vitest'
import { formatGrade, parseGrade } from '@/lib/decimal'

describe('decimal grade helpers', () => {
  it('parses a two-decimal string grade into a number', () => {
    expect(parseGrade('7.50')).toBe(7.5)
    expect(parseGrade('0.00')).toBe(0)
    expect(parseGrade('10')).toBe(10)
  })

  it('formats a number back to a two-decimal string', () => {
    expect(formatGrade(7.5)).toBe('7.50')
    expect(formatGrade(0)).toBe('0.00')
    expect(formatGrade(10)).toBe('10.00')
  })

  it('returns null for an empty or malformed grade string', () => {
    expect(parseGrade('')).toBeNull()
    expect(parseGrade('   ')).toBeNull()
    expect(parseGrade(null)).toBeNull()
    expect(parseGrade(undefined)).toBeNull()
    expect(parseGrade('abc')).toBeNull()
    expect(parseGrade('7.5.1')).toBeNull()
    expect(parseGrade('7.123')).toBeNull()
    expect(formatGrade(null)).toBeNull()
  })

  it('does not lose precision round-tripping 7.05', () => {
    expect(formatGrade(parseGrade('7.05'))).toBe('7.05')
    expect(parseGrade(formatGrade(7.05))).toBe(7.05)
  })
})
