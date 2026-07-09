<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { FileCheck2, KeyRound, ShieldCheck, TriangleAlert } from '@lucide/vue'
import { useBrandingStore } from '@/stores/branding'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/ThemeToggle.vue'

const { t } = useI18n()
const router = useRouter()
const branding = useBrandingStore()
const auth = useAuthStore()

const password = ref('')
const error = ref('')
const busy = ref(false)

function signInWithSso(): void {
  window.location.href = '/api/v1/auth/login'
}

async function submitEmergency(): Promise<void> {
  error.value = ''
  busy.value = true
  try {
    await auth.loginEmergency(password.value)
    await router.push('/exercises')
  } catch {
    error.value = t('auth.invalid')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="flex min-h-[calc(100vh-2.25rem)] items-center justify-center px-4 py-10">
    <div class="fixed right-6 top-10">
      <ThemeToggle />
    </div>

    <div class="w-full max-w-md">
      <div class="mb-6 flex justify-center">
        <div
          class="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500 shadow-lg shadow-indigo-500/25"
        >
          <FileCheck2 class="h-6 w-6 text-white" />
        </div>
      </div>
      <div class="mb-8 text-center">
        <h1 class="text-2xl font-semibold tracking-tight">{{ branding.appName }}</h1>
        <p class="mt-2 text-sm text-zinc-500">{{ t('auth.subtitle') }}</p>
      </div>

      <div
        class="space-y-3 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
      >
        <button
          type="button"
          class="flex h-11 w-full items-center justify-center gap-3 rounded-md bg-indigo-500 font-medium text-white transition hover:bg-indigo-400"
          @click="signInWithSso"
        >
          <ShieldCheck class="h-4 w-4" />
          <span>{{ t('auth.sso') }}</span>
        </button>

        <div class="flex items-center gap-3 py-1 text-xs text-zinc-500">
          <div class="h-px flex-1 bg-zinc-200 dark:bg-zinc-800"></div>
          <span>{{ t('auth.or') }}</span>
          <div class="h-px flex-1 bg-zinc-200 dark:bg-zinc-800"></div>
        </div>

        <form class="space-y-3" @submit.prevent="submitEmergency">
          <div class="flex items-center gap-1.5 text-xs font-medium text-zinc-500">
            <KeyRound class="h-3.5 w-3.5" />
            <span>{{ t('auth.emergencyHeading') }}</span>
          </div>
          <label for="emergency-password" class="sr-only">{{ t('auth.password') }}</label>
          <input
            id="emergency-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            :placeholder="t('auth.password')"
            class="h-11 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900"
          />
          <div
            v-if="error"
            class="alert-error flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
          >
            <TriangleAlert class="h-4 w-4 shrink-0" />
            <span>{{ error }}</span>
          </div>
          <button
            type="submit"
            :disabled="busy || !password"
            class="flex h-11 w-full items-center justify-center gap-2 rounded-md border border-zinc-200 font-medium transition hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-800 dark:hover:bg-zinc-800"
          >
            {{ t('auth.emergencySubmit') }}
          </button>
        </form>
      </div>

      <div class="mt-6 text-center text-xs text-zinc-500">
        Identity provider configured via <code class="text-zinc-400">OIDC_ISSUER_URL</code>
      </div>
    </div>
  </main>
</template>
