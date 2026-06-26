<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/AppShell.vue'

const { t } = useI18n()
</script>

<template>
  <AppShell :title="t('templates.title')">
    <p class="text-sm text-zinc-500">{{ t('templates.subtitle') }}</p>
  </AppShell>
</template>
