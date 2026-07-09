import { registerUnauthorizedHandler } from '@/services/http'
import { useAuthStore } from '@/stores/auth'

/** Wire the global 401 handler: clear the session and redirect to login. */
export function installAuthGuards(redirect: (path: string) => void): void {
  const auth = useAuthStore()
  registerUnauthorizedHandler(() => {
    auth.clear()
    redirect('/login')
  })
}
