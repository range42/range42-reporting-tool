/**
 * Character-budget helpers for rich-text sections, shared by the report
 * editor and any surface showing char counts. Counting matches the backend:
 * HTML stripped to plain text, whitespace collapsed, then trimmed.
 */
export function useCharBudget() {
  function plainLength(html: string): number {
    // Outside a DOM (SSR/node), fall back to the raw length — mirrors the
    // pre-extraction editor behaviour so JSDOM tests stay identical.
    if (typeof DOMParser === 'undefined') return html.length
    const doc = new DOMParser().parseFromString(html, 'text/html')
    return (doc.body.textContent ?? '').replace(/\s+/g, ' ').trim().length
  }

  const count = plainLength

  function overLimit(html: string, limit: number | null): boolean {
    return limit !== null && count(html) > limit
  }

  function remaining(html: string, limit: number | null): number | null {
    return limit === null ? null : limit - count(html)
  }

  return { plainLength, count, overLimit, remaining }
}
