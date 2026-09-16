<script setup lang="ts">
/**
 * Read-only renderer for one report section's submitted content.
 *
 * Presentational and prop-driven on purpose — no store access, no service calls — because it
 * is mounted several times on one screen (campaign pairing, cross-team compare), and a
 * component that reached for the evaluation store could only ever show one section.
 *
 * SECURITY: section content is writer-authored HTML, i.e. untrusted. It reaches `v-html`
 * only through `sanitize()`, never raw. `choice_values` are rendered as TEXT: they arrive as
 * plain strings and interpolating them as markup would reopen the hole sanitize just closed.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { sanitize } from '@/services/sanitize'
import type { GradableSection } from '@/services/evaluations'

const props = defineProps<{ section: GradableSection }>()

const { t } = useI18n()

const choices = computed<string[]>(() => props.section.choice_values ?? [])
const hasChoices = computed(() => choices.value.length > 0)
const safeContent = computed(() =>
  props.section.content === null ? '' : sanitize(props.section.content),
)
/** Empty means: nothing a reader could see — no chips, and no content once sanitized. */
const isEmpty = computed(() => !hasChoices.value && safeContent.value.trim() === '')
const charCount = computed(() => props.section.content_plain?.length ?? 0)
</script>

<template>
  <article
    :data-test="`content-pane-${section.report_section_id}`"
    class="rounded-lg border border-[var(--rt-border)] bg-[var(--rt-bg-elev)]"
  >
    <header
      class="flex items-baseline justify-between gap-3 border-b border-[var(--rt-border)] px-4 py-2.5"
    >
      <div class="min-w-0">
        <h3 class="truncate text-sm font-semibold">{{ section.name }}</h3>
        <p v-if="section.description" class="truncate text-xs text-[var(--rt-fg-muted)]">
          {{ section.description }}
        </p>
      </div>
      <span
        :data-test="`content-chars-${section.report_section_id}`"
        class="shrink-0 text-xs tabular-nums text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.charCount', { count: charCount }) }}
      </span>
    </header>

    <div class="px-4 py-3 text-sm">
      <ul v-if="hasChoices" class="flex flex-wrap gap-1.5">
        <li
          v-for="(choice, i) in choices"
          :key="`${section.report_section_id}-${i}`"
          :data-test="`content-chip-${section.report_section_id}-${i}`"
          class="rounded-full border border-[var(--rt-border)] px-2.5 py-0.5 text-xs"
        >
          {{ choice }}
        </li>
      </ul>

      <p
        v-else-if="isEmpty"
        :data-test="`content-empty-${section.report_section_id}`"
        class="text-xs italic text-[var(--rt-fg-muted)]"
      >
        {{ t('evaluations.emptySection') }}
      </p>

      <!-- eslint-disable-next-line vue/no-v-html -- sanitize() is the shared allowlist -->
      <div
        v-else
        :data-test="`content-body-${section.report_section_id}`"
        class="prose-rt max-w-none"
        v-html="safeContent"
      />
    </div>
  </article>
</template>
