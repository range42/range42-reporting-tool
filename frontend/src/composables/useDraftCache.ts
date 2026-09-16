import { createDraftCache, type DraftEntry } from '@/lib/draftCache'

/**
 * Per-section report drafts, keyed by `reportId:sectionDefId`.
 *
 * The mechanics live in `lib/draftCache.ts`, shared with `useGradeDraftCache`.
 */
export function useDraftCache(reportId: string) {
  const cache = createDraftCache<unknown>((sectionDefId) => `r42:draft:${reportId}:${sectionDefId}`)
  return {
    write: cache.save,
    read: (sectionDefId: string): DraftEntry<unknown> | null => cache.read(sectionDefId),
    clear: cache.clear,
    isNewerThanServer: cache.isNewerThanServer,
  }
}
