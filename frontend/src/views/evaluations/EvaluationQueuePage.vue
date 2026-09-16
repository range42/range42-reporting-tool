<script setup lang="ts">
/**
 * Route-level wrapper that gives the evaluator queue the same page frame as every other view.
 *
 * The frame lives here rather than in `EvaluationQueue.vue` because that component is also
 * mounted as a CHILD against rows the parent already holds — wrapping it directly would nest
 * one AppShell inside another.
 */
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/AppShell.vue'
import EvaluationQueue from '@/views/evaluations/EvaluationQueue.vue'

const { t } = useI18n()
</script>

<template>
  <AppShell :title="t('evaluations.queueTitle')">
    <EvaluationQueue />
  </AppShell>
</template>
