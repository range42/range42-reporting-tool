<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { FileCheck2 } from 'lucide-vue-next'
import { useBrandingStore } from '@/stores/branding'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/ThemeToggle.vue'

defineProps<{ title?: string }>()

const branding = useBrandingStore()
const auth = useAuthStore()

const initials = computed(() => {
  const name = (auth.user?.display_name || auth.user?.email || '').trim()
  const parts = name.split(/\s+/).filter(Boolean)
  const first = parts[0]?.[0] ?? ''
  const second = parts.length >= 2 ? (parts[1]?.[0] ?? '') : ''
  return (first + second || name.slice(0, 2) || '?').toUpperCase()
})
</script>

<template>
  <header
    class="sticky top-0 z-30 border-b border-zinc-200 bg-white/60 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/60"
  >
    <div class="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-6">
      <div class="flex items-center gap-3">
        <RouterLink
          to="/exercises"
          class="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-500"
        >
          <FileCheck2 class="h-4 w-4 text-white" />
        </RouterLink>
        <span class="font-semibold tracking-tight">{{ branding.appName }}</span>
        <template v-if="title">
          <span class="text-zinc-300 dark:text-zinc-700">/</span>
          <span class="text-sm font-medium text-zinc-600 dark:text-zinc-400">{{ title }}</span>
        </template>
      </div>
      <div class="flex items-center gap-2">
        <slot name="actions" />
        <ThemeToggle />
        <div
          v-if="auth.user"
          class="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/15 text-sm font-medium text-indigo-500"
        >
          {{ initials }}
        </div>
      </div>
    </div>
  </header>

  <main class="mx-auto max-w-7xl px-6 py-8">
    <slot />
  </main>
</template>
