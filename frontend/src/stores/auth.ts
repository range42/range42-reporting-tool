import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  completeOidcCallback,
  emergencyLogin,
  fetchMe,
  logoutSession,
  refreshSession,
  type AuthUser,
  type Session,
} from '@/services/auth'

const TOKEN_KEY = 'rt_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<AuthUser | null>(null)

  const isAuthenticated = computed(() => token.value !== null && user.value !== null)
  const isAdmin = computed(() => user.value?.is_global_admin === true)

  function setSession(s: Session): void {
    token.value = s.access_token
    user.value = s.user
    localStorage.setItem(TOKEN_KEY, s.access_token)
  }

  function clear(): void {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  async function loginEmergency(password: string): Promise<void> {
    setSession(await emergencyLogin(password))
  }

  async function completeOidc(code: string, state: string): Promise<void> {
    setSession(await completeOidcCallback(code, state))
  }

  async function refresh(): Promise<void> {
    if (token.value) setSession(await refreshSession(token.value))
  }

  /** Re-read the persisted token and validate it via /auth/me; clear if rejected. */
  async function rehydrate(): Promise<void> {
    const persisted = localStorage.getItem(TOKEN_KEY)
    if (!persisted) {
      clear()
      return
    }
    token.value = persisted
    try {
      user.value = await fetchMe(persisted)
    } catch {
      clear()
    }
  }

  async function logout(): Promise<void> {
    if (token.value) {
      try {
        await logoutSession(token.value)
      } catch {
        // best-effort; clear locally regardless
      }
    }
    clear()
  }

  return {
    token,
    user,
    isAuthenticated,
    isAdmin,
    setSession,
    clear,
    loginEmergency,
    completeOidc,
    refresh,
    rehydrate,
    logout,
  }
})
