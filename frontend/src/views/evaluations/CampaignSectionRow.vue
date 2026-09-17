<script setup lang="ts">
/**
 * One section, paired: the previous cycle's read-only card on the left, the current
 * (editable) SectionGradeCard on the right (D12/D13). Extracted from CampaignEvaluation.vue
 * to keep that view orchestration-only.
 */
import { useI18n } from 'vue-i18n'
import SectionGradeCard from '@/views/evaluations/SectionGradeCard.vue'
import PreviousSectionCard from '@/views/evaluations/PreviousSectionCard.vue'
import type { ReportSection } from '@/services/reports'
import type { SectionGrade } from '@/services/evaluations'

defineProps<{
  sectionDefId: string
  currentSectionId: string
  previousSection: ReportSection | null
  hasOwnPreviousEvaluation: boolean
  previousGrade: SectionGrade | null
}>()

const emit = defineEmits<{ registerRow: [el: Element | null] }>()

const { t } = useI18n()
</script>

<template>
  <div
    :data-test="`pair-row-${sectionDefId}`"
    class="grid grid-cols-1 gap-3 md:grid-cols-2"
    :ref="(el) => emit('registerRow', el as Element | null)"
  >
    <PreviousSectionCard
      v-if="previousSection"
      :section="previousSection"
      :has-own-previous-evaluation="hasOwnPreviousEvaluation"
      :grade="previousGrade"
    />
    <p
      v-else
      :data-test="`prev-empty-${sectionDefId}`"
      class="rounded-lg border border-dashed border-[var(--rt-border)] p-3 text-xs italic text-[var(--rt-fg-muted)]"
    >
      {{ t('evaluations.campaignFirstReport') }}
    </p>

    <SectionGradeCard :section-id="currentSectionId" />
  </div>
</template>
