import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createApp, defineComponent, h, type App } from 'vue'
import { bootstrap } from '@/boot'
import { router } from '@/router'

const USER = {
  id: 'u1',
  email: 'alice@range42.local',
  display_name: 'alice',
  avatar_url: null,
  is_global_admin: false,
}

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** A bare app with a real mount target, so bootstrap can run to completion. */
function makeApp(): App {
  const host = document.createElement('div')
  host.id = 'app'
  document.body.appendChild(host)
  return createApp(defineComponent({ render: () => h('div') }))
}

describe('bootstrap', () => {
  let app: App | undefined

  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    app?.unmount()
    app = undefined
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
    window.history.replaceState({}, '', '/')
  })

  it('rehydrates the session before installing the router', async () => {
    // Installing the router starts the initial navigation, which runs the guards, and
    // `isAuthenticated` needs a token AND a fetched user — so rehydration must come first.
    localStorage.setItem('rt_token', 'tok')

    const calls: string[] = []
    let releaseMe: (() => void) | undefined
    const mePending = new Promise<void>((resolve) => {
      releaseMe = resolve
    })

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/auth/me')) {
          calls.push('auth/me:start')
          await mePending
          calls.push('auth/me:done')
          return envelope(USER)
        }
        return envelope({})
      }),
    )

    app = makeApp()
    const use = vi.spyOn(app, 'use')
    const routerInstalled = (): boolean => use.mock.calls.some(([plugin]) => plugin === router)
    const booting = bootstrap(app)

    await Promise.resolve()
    await Promise.resolve()
    expect(calls).toContain('auth/me:start')
    expect(routerInstalled()).toBe(false)

    releaseMe?.()
    await booting

    expect(calls).toEqual(['auth/me:start', 'auth/me:done'])
    expect(routerInstalled()).toBe(true)
  })

  it('a page load carrying a valid token does not land on the login page', async () => {
    localStorage.setItem('rt_token', 'tok')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes('/auth/me') ? envelope(USER) : envelope({}),
      ),
    )

    app = makeApp()
    await bootstrap(app)

    expect(router.currentRoute.value.path).not.toBe('/login')
  })

  it('a page load on an evaluation deep link stays on the evaluation route', async () => {
    // Arrange: a reload lands straight on a `requiresEvaluator` route, so nothing has
    // cached the exercise capabilities the guard reads.
    const path = '/exercises/ex1/reports/r1/evaluations/ev1'
    localStorage.setItem('rt_token', 'tok')
    window.history.replaceState({}, '', path)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/auth/me')) return envelope(USER)
        if (url.endsWith('/exercises/ex1/me'))
          return envelope({ is_global_admin: false, capabilities: ['evaluations:write'] })
        return envelope({
          report_name: 'r',
          sections: [],
          grade_version: 1,
          overall_grade: null,
          graded_section_count: 0,
        })
      }),
    )

    // Act: fresh modules, because vue-router only runs its initial navigation for the
    // first app a router instance is installed into.
    vi.resetModules()
    const [boot, freshRouter] = await Promise.all([import('@/boot'), import('@/router')])
    app = makeApp()
    await boot.bootstrap(app)

    // Assert
    expect(freshRouter.router.currentRoute.value.path).toBe(path)
  })
})
