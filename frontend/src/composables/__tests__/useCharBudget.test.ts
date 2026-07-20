import { describe, expect, it } from 'vitest'
import { useCharBudget } from '@/composables/useCharBudget'

describe('useCharBudget', () => {
  const budget = useCharBudget()

  it('counts plain text, stripping tags and collapsing whitespace', () => {
    expect(budget.count('<p>hello   <b>world</b></p>')).toBe('hello world'.length)
    expect(budget.plainLength('  <p>\n a \n b </p>')).toBe('a b'.length)
    expect(budget.count('')).toBe(0)
  })

  it('overLimit is false at the limit, true over it, false without a limit', () => {
    expect(budget.overLimit('<p>abcde</p>', 5)).toBe(false)
    expect(budget.overLimit('<p>abcdef</p>', 5)).toBe(true)
    expect(budget.overLimit('<p>abcdef</p>', null)).toBe(false)
  })

  it('remaining is limit minus count, or null without a limit', () => {
    expect(budget.remaining('<p>abc</p>', 5)).toBe(2)
    expect(budget.remaining('<p>abcdef</p>', 5)).toBe(-1)
    expect(budget.remaining('<p>abc</p>', null)).toBeNull()
  })
})
