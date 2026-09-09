/**
 * The localStorage draft mechanics both draft caches share: key building, JSON round-trip,
 * and the "is my unsaved work newer than the server's copy?" comparison.
 *
 * Only the KEY SHAPE differs between callers, so that is the one thing injected. Report
 * drafts are keyed by report+section, grade drafts by evaluation+section; everything else
 * — including the decision to treat an unreadable payload as absent — is identical, and
 * duplicating it is how the two drift into disagreeing about a corrupt entry.
 */

export interface DraftEntry<T> {
  value: T
  editedAt: string
}

export interface DraftCache<T> {
  save: (id: string, value: T, editedAt: string) => void
  read: (id: string) => DraftEntry<T> | null
  clear: (id: string) => void
  isNewerThanServer: (id: string, serverUpdatedAt: string) => boolean
}

/** A stored entry must be an object carrying an `editedAt` string, or we cannot compare it
 *  against the server and it is worthless. Anything else is treated as absent. */
function isDraftEntry(parsed: unknown): parsed is DraftEntry<unknown> {
  return (
    typeof parsed === 'object' &&
    parsed !== null &&
    !Array.isArray(parsed) &&
    typeof (parsed as { editedAt?: unknown }).editedAt === 'string'
  )
}

export function createDraftCache<T>(keyFor: (id: string) => string): DraftCache<T> {
  function save(id: string, value: T, editedAt: string): void {
    localStorage.setItem(keyFor(id), JSON.stringify({ value, editedAt } satisfies DraftEntry<T>))
  }

  /**
   * The stored draft, or null.
   *
   * A corrupt or foreign payload returns null rather than throwing: this runs on the render
   * path of a view whose whole job is to recover unsaved work, and a parse error there would
   * take down the editor over a cache entry nobody can use anyway.
   */
  function read(id: string): DraftEntry<T> | null {
    const raw = localStorage.getItem(keyFor(id))
    if (raw === null) return null
    try {
      const parsed: unknown = JSON.parse(raw)
      return isDraftEntry(parsed) ? (parsed as DraftEntry<T>) : null
    } catch {
      return null
    }
  }

  function clear(id: string): void {
    localStorage.removeItem(keyFor(id))
  }

  function isNewerThanServer(id: string, serverUpdatedAt: string): boolean {
    const entry = read(id)
    if (entry === null) return false
    const edited = new Date(entry.editedAt).getTime()
    const server = new Date(serverUpdatedAt).getTime()
    // An unparseable timestamp on either side cannot prove the draft is newer.
    if (Number.isNaN(edited) || Number.isNaN(server)) return false
    return edited > server
  }

  return { save, read, clear, isNewerThanServer }
}
