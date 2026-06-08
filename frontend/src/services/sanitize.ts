/**
 * Shared HTML-sanitization allowlist (single source of truth, frontend side).
 *
 * This MUST stay in sync with `backend/app/core/sanitize_policy.py`. The two
 * allowlists describe the same policy on each stack (nh3 on the backend,
 * DOMPurify here). Covers headings, lists, tables, code, images, and links.
 */
import DOMPurify from 'dompurify'

export const ALLOWED_TAGS: readonly string[] = [
  // headings
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  // text + structure
  'p',
  'br',
  'hr',
  'span',
  'div',
  'blockquote',
  'strong',
  'em',
  'b',
  'i',
  'u',
  's',
  'sub',
  'sup',
  // lists
  'ul',
  'ol',
  'li',
  // tables
  'table',
  'thead',
  'tbody',
  'tfoot',
  'tr',
  'th',
  'td',
  'caption',
  // code
  'code',
  'pre',
  // media + links
  'img',
  'a',
]

export const ALLOWED_ATTR: readonly string[] = [
  'class',
  'href',
  'title',
  'rel',
  'target',
  'src',
  'alt',
  'width',
  'height',
  'colspan',
  'rowspan',
  'scope',
]

/** Sanitize untrusted HTML against the shared allowlist. */
export function sanitize(dirty: string): string {
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: [...ALLOWED_TAGS],
    ALLOWED_ATTR: [...ALLOWED_ATTR],
  })
}
