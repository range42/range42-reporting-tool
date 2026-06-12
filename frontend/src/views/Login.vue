<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBrandingStore } from '@/stores/branding'
import { useAuthStore } from '@/stores/auth'

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
  <main class="min-h-screen flex items-center justify-center bg-base-200 p-4">
    <div class="card bg-base-100 shadow-lg w-full max-w-md">
      <div class="card-body">
        <h1 class="card-title justify-center text-2xl mb-2">{{ branding.appName }}</h1>

        <button class="btn btn-primary w-full" @click="signInWithSso">{{ t('auth.sso') }}</button>

        <div class="divider text-xs opacity-60">{{ t('auth.or') }}</div>

        <form class="space-y-3" @submit.prevent="submitEmergency">
          <h2 class="text-sm font-semibold opacity-70">{{ t('auth.emergencyHeading') }}</h2>
          <div class="form-control">
            <label class="label"
              ><span class="label-text">{{ t('auth.password') }}</span></label
            >
            <input
              v-model="password"
              type="password"
              class="input input-bordered w-full"
              autocomplete="current-password"
            />
          </div>
          <div v-if="error" class="alert alert-error text-sm">
            <span>{{ error }}</span>
          </div>
          <button type="submit" class="btn btn-outline w-full" :disabled="busy || !password">
            {{ t('auth.emergencySubmit') }}
          </button>
        </form>
      </div>
    </div>
  </main>
</template>
