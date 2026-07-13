interface DraftEntry {
  value: unknown
  editedAt: string
}

export function useDraftCache(reportId: string) {
  const keyFor = (sectionDefId: string): string => `r42:draft:${reportId}:${sectionDefId}`

  function write(sectionDefId: string, value: unknown, editedAt: string): void {
    localStorage.setItem(
      keyFor(sectionDefId),
      JSON.stringify({ value, editedAt } satisfies DraftEntry),
    )
  }
  function read(sectionDefId: string): DraftEntry | null {
    const raw = localStorage.getItem(keyFor(sectionDefId))
    return raw ? (JSON.parse(raw) as DraftEntry) : null
  }
  function clear(sectionDefId: string): void {
    localStorage.removeItem(keyFor(sectionDefId))
  }
  function isNewerThanServer(sectionDefId: string, serverUpdatedAt: string): boolean {
    const entry = read(sectionDefId)
    return entry ? new Date(entry.editedAt).getTime() > new Date(serverUpdatedAt).getTime() : false
  }
  return { write, read, clear, isNewerThanServer }
}
