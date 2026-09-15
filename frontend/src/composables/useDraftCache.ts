import { createDraftCache, type DraftEntry } from '@/lib/draftCache'

/**
 * Per-section report drafts (WP3 Task 12), keyed by `reportId:sectionDefId`.
 *
 * The mechanics live in `lib/draftCache.ts`, shared with `useGradeDraftCache`. The public
 * method here stays `write` rather than the helper's `save`: `ReportEditor.vue` is the only
 * caller and renaming it buys nothing but churn in a shipped view.
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
