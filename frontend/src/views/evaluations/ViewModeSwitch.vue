<script setup lang="ts">
/**
 * Single ↔ Campaign switch for one evaluation.
 *
 * The campaign target is passed in rather than built here, and is null when the route does
 * not exist: W5-6 registers `evaluation-campaign`, and a `RouterLink` pointing at an
 * unregistered name throws while resolving, taking the whole view down. Null renders a
 * disabled control with a reason instead.
 */
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationNamedRaw } from 'vue-router'

defineProps<{ campaignTo: RouteLocationNamedRaw | null }>()

const { t } = useI18n()
</script>

<template>
  <nav
    :aria-label="t('evaluations.title')"
    class="inline-flex rounded-md border border-[var(--rt-border)]"
  >
    <span
      data-test="mode-single"
      aria-current="page"
      class="px-3 py-1 text-xs font-medium bg-[var(--rt-accent)] text-white"
    >
      {{ t('evaluations.modeSingle') }}
    </span>
    <RouterLink
      v-if="campaignTo"
      data-test="mode-campaign"
      :to="campaignTo"
      class="border-l border-[var(--rt-border)] px-3 py-1 text-xs transition-opacity duration-150 hover:opacity-80"
    >
      {{ t('evaluations.modeCampaign') }}
    </RouterLink>
    <span
      v-else
      data-test="mode-campaign-disabled"
      :title="t('evaluations.modeCampaignUnavailable')"
      class="border-l border-[var(--rt-border)] px-3 py-1 text-xs opacity-50"
    >
      {{ t('evaluations.modeCampaign') }}
    </span>
  </nav>
</template>
