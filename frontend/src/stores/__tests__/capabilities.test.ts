import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCapabilitiesStore } from '@/stores/capabilities'
import * as exercises from '@/services/exercises'

describe('capabilities store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('tracks capabilities per exercise', () => {
    const c = useCapabilitiesStore()
    c.set('ex1', ['reports:approve', 'reports:write'])
    expect(c.has('ex1', 'reports:write')).toBe(true)
    expect(c.canApproveReports('ex1')).toBe(true)
    expect(c.canApproveReports('ex2')).toBe(false) // unknown exercise -> false
  })

  it('load fetches from /me and caches the capabilities', async () => {
    vi.spyOn(exercises, 'getMyCapabilities').mockResolvedValue({
      is_global_admin: false,
      capabilities: ['reports:approve'],
    })
    const c = useCapabilitiesStore()
    await c.load('tok', 'ex1')
    expect(c.canApproveReports('ex1')).toBe(true)
  })
})
