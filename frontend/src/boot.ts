import type { App } from 'vue'
import { createPinia } from 'pinia'
import { router } from '@/router'
import { i18n } from '@/i18n'
import { useBrandingStore } from '@/stores/branding'
import { useAuthStore } from '@/stores/auth'
import { installAuthGuards } from '@/stores/auth_boot'
import { useTheme } from '@/composables/useTheme'

/**
 * Wire and start the app.
 *
 * Order matters: installing the router starts the initial navigation, which runs
 * the guards. `isAuthenticated` needs BOTH a token and a fetched user, so the
 * session has to be rehydrated *before* the router is installed — otherwise a
 * page load with a perfectly valid persisted token resolves to `/login`, and
 * nothing re-evaluates the route once `/auth/me` comes back.
 *
 * Takes the app so the ordering is testable; see `__tests__/boot.test.ts`.
 */
export async function bootstrap(app: App, selector = '#app'): Promise<void> {
  useTheme().init()
  app.use(createPinia())
  installAuthGuards((path) => void router.push(path))

  await Promise.all([useBrandingStore().load(), useAuthStore().rehydrate()])

  app.use(router)
  app.use(i18n)
  await router.isReady()
  app.mount(selector)
}
