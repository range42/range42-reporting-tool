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

  it('keeps img src pointing at our own attachment download endpoint', () => {
    const src = '/api/v1/exercises/e1/reports/r1/attachments/a1/download'
    expect(sanitize(`<img src="${src}" alt="x">`)).toContain(`src="${src}"`)
  })

  it.each([
    'https://evil.example/x.png',
    '//evil.example/x.png',
    'data:image/png;base64,AAAA',
    '/api/v1/exercises/e1/reports/r1/attachments/../../../secrets',
    '/etc/passwd',
  ])('drops img src outside the attachment path: %s', (src) => {
    expect(sanitize(`<img src="${src}" alt="x">`)).not.toContain('src=')
  })
})
