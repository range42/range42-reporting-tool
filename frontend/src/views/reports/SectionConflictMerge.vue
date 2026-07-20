<script setup lang="ts">
/**
 * 3-way conflict resolution panel for a report section that hit a stale-version
 * 409. Purely presentational: shows Base / Yours / Server and emits the chosen
 * resolution — the editor owns versions, saving, and the draft cache.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { GitMerge } from '@lucide/vue'

const props = defineProps<{
  base: string
  local: string
  server: string
  serverVersion: number
  fieldType: 'rich_text' | 'choice'
  testId: string
}>()

const emit = defineEmits<{
  keepMine: []
  useServer: []
  resolvedManual: [content: string]
}>()

const { t } = useI18n()

const manualOpen = ref(false)
const manualContent = ref('')

function openManual(): void {
  manualContent.value = props.local
  manualOpen.value = true
}

const panes = [
  { key: 'base', label: 'reports.merge.base', value: props.base },
  { key: 'local', label: 'reports.merge.yours', value: props.local },
  { key: 'server', label: 'reports.merge.server', value: props.server },
] as const
</script>

<template>
  <div
    :data-test="`merge-${testId}`"
    class="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm"
  >
    <p class="mb-3 flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-300">
      <GitMerge class="h-4 w-4 shrink-0" />
      {{ t('reports.merge.title') }}
    </p>

    <div class="mb-3 grid gap-2 sm:grid-cols-3">
      <div
        v-for="pane in panes"
        :key="pane.key"
        class="rounded border border-amber-500/20 bg-white/60 p-2 dark:bg-zinc-900/60"
      >
        <p class="mb-1 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
          {{ t(pane.label) }}
        </p>
        <p
          class="whitespace-pre-wrap break-words font-mono text-xs text-zinc-700 dark:text-zinc-300"
        >
          {{ pane.value }}
        </p>
      </div>
    </div>

    <div v-if="manualOpen" class="mb-3">
      <textarea
        v-model="manualContent"
        :data-test="`merge-editor-${testId}`"
        rows="5"
        class="w-full rounded border border-amber-500/30 bg-white p-2 font-mono text-xs dark:bg-zinc-900"
      />
    </div>

    <div class="flex flex-wrap justify-end gap-2">
      <template v-if="!manualOpen">
        <button
          type="button"
          :data-test="`merge-keep-mine-${testId}`"
          class="rounded border border-amber-400 px-2 py-1 text-xs font-medium text-amber-700 transition hover:bg-amber-500/10 dark:text-amber-300"
          @click="emit('keepMine')"
        >
          {{ t('reports.merge.keepMine') }}
        </button>
        <button
          type="button"
          :data-test="`merge-use-server-${testId}`"
          class="rounded border border-amber-400 px-2 py-1 text-xs font-medium text-amber-700 transition hover:bg-amber-500/10 dark:text-amber-300"
          @click="emit('useServer')"
        >
          {{ t('reports.merge.useServer') }}
        </button>
        <button
          v-if="fieldType === 'rich_text'"
          type="button"
          :data-test="`merge-manual-${testId}`"
          class="rounded px-2 py-1 text-xs text-zinc-500 transition hover:bg-zinc-500/10"
          @click="openManual"
        >
          {{ t('reports.merge.mergeManual') }}
        </button>
      </template>
      <template v-else>
        <button
          type="button"
          class="rounded px-2 py-1 text-xs text-zinc-500 transition hover:bg-zinc-500/10"
          @click="manualOpen = false"
        >
          {{ t('reports.merge.cancel') }}
        </button>
        <button
          type="button"
          :data-test="`merge-apply-${testId}`"
          class="rounded border border-amber-400 px-2 py-1 text-xs font-medium text-amber-700 transition hover:bg-amber-500/10 dark:text-amber-300"
          @click="emit('resolvedManual', manualContent)"
        >
          {{ t('reports.merge.apply') }}
        </button>
      </template>
    </div>
  </div>
</template>
