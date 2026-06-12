<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const error = ref('')

onMounted(async () => {
  const code = String(route.query.code ?? '')
  const state = String(route.query.state ?? '')
  if (!code || !state) {
    error.value = t('auth.callbackFailed')
    return
  }
  try {
    await auth.completeOidc(code, state)
    await router.push('/exercises')
  } catch {
    error.value = t('auth.callbackFailed')
  }
})
</script>

<template>
  <main class="min-h-screen flex items-center justify-center bg-base-200">
    <div v-if="!error" class="flex items-center gap-3">
      <span class="loading loading-spinner loading-md"></span>
      <span>{{ t('auth.completing') }}</span>
    </div>
    <div v-else class="alert alert-error max-w-md">
      <span>{{ error }}</span>
    </div>
  </main>
</template>
