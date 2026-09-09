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
  })

  it('rehydrates the session before installing the router', async () => {
    // Installing the router starts the initial navigation, which runs the guards.
    // `isAuthenticated` needs a token AND a fetched user, so rehydrating after
    // installation sends a page load with a valid token to /login, and nothing
    // re-evaluates the route once /auth/me answers.
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
})
