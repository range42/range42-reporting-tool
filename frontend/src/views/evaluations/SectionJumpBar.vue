<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  sections: { section_def_id: string; name: string }[]
  activeSectionId: string | null
}>()
const emit = defineEmits<{ jump: [sectionDefId: string] }>()

const { t } = useI18n()
</script>

<template>
  <nav :aria-label="t('evaluations.campaignJumpAriaLabel')">
    <ol class="flex flex-wrap gap-1.5">
      <li v-for="s in sections" :key="s.section_def_id">
        <a
          href="#"
          :data-test="`jump-${s.section_def_id}`"
          :aria-current="s.section_def_id === activeSectionId ? 'true' : undefined"
          :class="[
            'rounded-full border px-2.5 py-0.5 text-xs transition',
            s.section_def_id === activeSectionId
              ? 'border-[var(--rt-accent)] text-[var(--rt-accent)]'
              : 'border-[var(--rt-border)] hover:bg-[var(--rt-border)]',
          ]"
          @click.prevent="emit('jump', s.section_def_id)"
        >
          {{ s.name }}
        </a>
      </li>
    </ol>
  </nav>
</template>
