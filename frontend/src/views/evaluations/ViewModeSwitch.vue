<script setup lang="ts">
/**
 * Single ↔ Campaign switch for one evaluation.
 *
 * The campaign target is passed in rather than built here, and is null while the
 * `evaluation-campaign` route is unregistered: a `RouterLink` pointing at an unregistered name
 * throws while resolving, taking the whole view down. Null renders a disabled control instead.
 *
 * `mode` picks which side is "current" (a plain `<span aria-current>`, not a link) — 'single'
 * (the default, unchanged from before this existed) for `SingleEvaluation.vue`, 'campaign' for
 * `CampaignEvaluation.vue`, which then needs `singleTo` to link back.
 */
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationNamedRaw } from 'vue-router'

withDefaults(
  defineProps<{
    campaignTo: RouteLocationNamedRaw | null
    mode?: 'single' | 'campaign'
    singleTo?: RouteLocationNamedRaw | null
  }>(),
  { mode: 'single', singleTo: null },
)

const { t } = useI18n()
</script>

<template>
  <nav
    :aria-label="t('evaluations.title')"
    class="inline-flex rounded-md border border-[var(--rt-border)]"
  >
    <span
      v-if="mode === 'single'"
      data-test="mode-single"
      aria-current="page"
      class="px-3 py-1 text-xs font-medium bg-[var(--rt-accent)] text-white"
    >
      {{ t('evaluations.modeSingle') }}
    </span>
    <RouterLink
      v-else-if="singleTo"
      data-test="mode-single"
      :to="singleTo"
      class="px-3 py-1 text-xs transition-opacity duration-150 hover:opacity-80"
    >
      {{ t('evaluations.modeSingle') }}
    </RouterLink>

    <RouterLink
      v-if="mode === 'single' && campaignTo"
      data-test="mode-campaign"
      :to="campaignTo"
      class="border-l border-[var(--rt-border)] px-3 py-1 text-xs transition-opacity duration-150 hover:opacity-80"
    >
      {{ t('evaluations.modeCampaign') }}
    </RouterLink>
    <span
      v-else-if="mode === 'single'"
      data-test="mode-campaign-disabled"
      :title="t('evaluations.modeCampaignUnavailable')"
      class="border-l border-[var(--rt-border)] px-3 py-1 text-xs opacity-50"
    >
      {{ t('evaluations.modeCampaign') }}
    </span>
    <span
      v-else
      data-test="mode-campaign"
      aria-current="page"
      class="border-l border-[var(--rt-border)] px-3 py-1 text-xs font-medium bg-[var(--rt-accent)] text-white"
    >
      {{ t('evaluations.modeCampaign') }}
    </span>
  </nav>
</template>
