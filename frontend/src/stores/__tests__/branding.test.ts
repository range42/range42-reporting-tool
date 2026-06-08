import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useBrandingStore } from '@/stores/branding'

describe('branding store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads config and applies primary color', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ data: { app_name: 'CR', logo_url: '', primary_color: '#abcdef' } }),
            { status: 200 },
          ),
      ),
    )
    const store = useBrandingStore()
    await store.load()
    expect(store.appName).toBe('CR')
    expect(document.documentElement.style.getPropertyValue('--rt-primary')).toBe('#abcdef')
  })

  it('falls back to defaults when config fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network')
      }),
    )
    const store = useBrandingStore()
    await store.load()
    expect(store.appName).toBe('Reporting Tool')
  })
})
