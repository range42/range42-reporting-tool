import { ref, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export interface UseActiveSectionOptions {
  /** URL query param key the active section is written to (default `'section'`). */
  queryKey?: string
}

export interface UseActiveSection {
  activeSectionId: Ref<string | null>
  /** Bind as a template ref callback on each paired section row: `:ref="(el) => registerRow(id, el)"`. */
  registerRow: (sectionId: string, el: Element | null) => void
  jumpTo: (sectionId: string) => void
  /** The caller wires this into its own unmount hook — this composable has no lifecycle
   * hooks of its own, so it works the same whether called from a component or a plain test. */
  disconnect: () => void
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

/**
 * Section-paired active-tracking for the campaign two-pane view (D12): no pixel-offset scroll
 * syncing, no scroll event listeners — IntersectionObserver is the only mechanism, and a jump
 * link scrolls the paired row into view directly.
 */
export function useActiveSection(
  sectionIds: Ref<readonly string[]>,
  options: UseActiveSectionOptions = {},
): UseActiveSection {
  const queryKey = options.queryKey ?? 'section'
  const route = useRoute()
  const router = useRouter()

  const activeSectionId = ref<string | null>(sectionIds.value[0] ?? null)
  const rows = new Map<string, Element>()

  function setActive(sectionId: string): void {
    if (activeSectionId.value === sectionId) return
    activeSectionId.value = sectionId
    void router.replace({ query: { ...route.query, [queryKey]: sectionId } })
  }

  const observer: IntersectionObserver | null =
    typeof IntersectionObserver === 'undefined'
      ? null
      : new IntersectionObserver((entries) => {
          const hit = entries.find((e) => e.isIntersecting)
          if (!hit) return
          for (const [sectionId, el] of rows) {
            if (el === hit.target) {
              setActive(sectionId)
              return
            }
          }
        })

  function registerRow(sectionId: string, el: Element | null): void {
    const prior = rows.get(sectionId)
    if (prior) observer?.unobserve(prior)
    if (el === null) {
      rows.delete(sectionId)
      return
    }
    rows.set(sectionId, el)
    observer?.observe(el)
  }

  function jumpTo(sectionId: string): void {
    rows
      .get(sectionId)
      ?.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }

  function disconnect(): void {
    observer?.disconnect()
  }

  return { activeSectionId, registerRow, jumpTo, disconnect }
}
