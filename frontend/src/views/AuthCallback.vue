<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Loader, TriangleAlert } from '@lucide/vue'
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
  <main class="flex min-h-[calc(100vh-2.25rem)] items-center justify-center px-4">
    <div v-if="!error" class="flex items-center gap-3 text-zinc-500">
      <Loader class="h-5 w-5 animate-spin" />
      <span>{{ t('auth.completing') }}</span>
    </div>
    <div
      v-else
      class="alert-error flex max-w-md items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>
  </main>
</template>
