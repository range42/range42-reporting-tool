<script setup lang="ts">
import { useBrandingStore } from '@/stores/branding'
const branding = useBrandingStore()
</script>
<template>
  <main class="p-8">
    <h1 class="text-2xl font-bold">{{ branding.appName }}</h1>
    <p class="opacity-70">Skeleton shell — ready for feature slices.</p>
  </main>
</template>
