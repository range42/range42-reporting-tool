<script setup lang="ts">
/**
 * Placeholder surface for the AI pre-check.
 *
 * MOUNTED ONLY WHEN AI IS AVAILABLE. There is no `GET /ai/status` endpoint yet, so nothing
 * mounts this today and the evaluator sees no AI affordance at all: an assistive feature that
 * is switched off must be absent, not present-and-broken.
 */
import { useI18n } from 'vue-i18n'

defineProps<{ sectionId: string }>()

const { t } = useI18n()
</script>

<template>
  <aside
    :data-test="`ai-precheck-${sectionId}`"
    data-test-kind="ai-precheck"
    class="rounded-md border border-dashed border-[var(--rt-border)] px-3 py-2 text-xs text-[var(--rt-fg-muted)]"
  >
    {{ t('evaluations.aiPrecheck') }}
    <slot />
  </aside>
</template>
