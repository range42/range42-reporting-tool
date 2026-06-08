import { describe, expect, it } from 'vitest'
import { ALLOWED_ATTR, ALLOWED_TAGS, sanitize } from '@/services/sanitize'

describe('sanitize allowlist', () => {
  it('allowlist is non-empty and covers core tags', () => {
    expect(ALLOWED_TAGS.length).toBeGreaterThan(0)
    expect(ALLOWED_TAGS).toContain('table')
    expect(ALLOWED_TAGS).toContain('code')
    expect(ALLOWED_TAGS).toContain('img')
  })

  it('attribute allowlist is non-empty', () => {
    expect(ALLOWED_ATTR.length).toBeGreaterThan(0)
    expect(ALLOWED_ATTR).toContain('href')
    expect(ALLOWED_ATTR).toContain('src')
  })

  it('strips disallowed markup', () => {
    expect(sanitize('<p>ok</p><script>alert(1)</script>')).toBe('<p>ok</p>')
  })
})
