import type { App } from 'vue'
import { createPinia } from 'pinia'
import { router } from '@/router'
import { exerciseIdFromPath } from '@/router/guards'
import { i18n } from '@/i18n'
import { useBrandingStore } from '@/stores/branding'
import { useAuthStore } from '@/stores/auth'
import { useCapabilitiesStore } from '@/stores/capabilities'
import { installAuthGuards } from '@/stores/auth_boot'
import { useTheme } from '@/composables/useTheme'

/** Cache the caller's capabilities for the exercise the landing path is scoped to, if any. */
async function primeCapabilities(path: string): Promise<void> {
  const { token } = useAuthStore()
  const exerciseId = exerciseIdFromPath(path)
  if (!token || !exerciseId) return
  // A failed load must not block boot: the guards then fall back to the exercise picker.
  await useCapabilitiesStore()
    .load(token, exerciseId)
    .catch(() => undefined)
}

/**
 * Wire and start the app.
 *
 * ORDER MATTERS: installing the router starts the initial navigation, which runs the guards.
 * `isAuthenticated` needs BOTH a token and a fetched user, so the session must be rehydrated
 * *before* the router is installed, or a page load with a valid persisted token resolves to
 * `/login` and nothing re-evaluates the route. The same holds for the per-exercise
 * capabilities the `requiresApprover` / `requiresEvaluator` gates read.
 *
 * Takes the app so the ordering is testable; see `__tests__/boot.test.ts`.
 */
export async function bootstrap(app: App, selector = '#app'): Promise<void> {
  useTheme().init()
  app.use(createPinia())
  installAuthGuards((path) => void router.push(path))

  await Promise.all([useBrandingStore().load(), useAuthStore().rehydrate()])
  await primeCapabilities(window.location.pathname)

  app.use(router)
  app.use(i18n)
  await router.isReady()
  app.mount(selector)
}
