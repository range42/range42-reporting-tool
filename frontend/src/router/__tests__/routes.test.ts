import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { RouteRecordRaw } from 'vue-router'
import { router } from '@/router'

type Loader = () => Promise<{ default: unknown }>

const lazyRoutes = router.options.routes.filter(
  (r): r is RouteRecordRaw & { component: Loader } => typeof r.component === 'function',
)

describe('route table', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it.each(lazyRoutes.map((r) => [r.path, r.component] as const))(
    '%s lazy-loads a component',
    async (_path, load) => {
      const mod = await (load as Loader)()
      expect(mod.default).toBeTruthy()
    },
  )

  it('sends an unauthenticated visitor on a protected route to the login page', async () => {
    await router.push('/settings/roles')
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
