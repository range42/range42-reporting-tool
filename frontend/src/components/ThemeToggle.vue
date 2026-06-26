<script setup lang="ts">
import { SunMoon } from '@lucide/vue'
import { useTheme } from '@/composables/useTheme'

const { toggle } = useTheme()
</script>
<template>
  <button
    type="button"
    title="Toggle theme"
    class="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-200 transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
    @click="toggle"
  >
    <SunMoon class="h-4 w-4" />
  </button>
</template>
