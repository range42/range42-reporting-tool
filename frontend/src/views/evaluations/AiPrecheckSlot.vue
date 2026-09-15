<script setup lang="ts">
/**
 * Placeholder surface for the AI pre-check (D9).
 *
 * MOUNTED ONLY WHEN AI IS AVAILABLE. `GET /ai/status` is W5-8's to build (#167), so today
 * nothing mounts this and the evaluator sees no AI affordance at all — which is the point of
 * D9: an assistive feature that is switched off must be absent, not present-and-broken. The
 * slot exists so W5-8 has a seam to fill rather than a view to restructure.
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
