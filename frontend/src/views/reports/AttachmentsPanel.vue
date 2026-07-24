<script setup lang="ts">
/**
 * Per-section attachment list (WP3 S9). Presentational: the parent owns the
 * attachment collection and service calls; this panel only renders the slice
 * for its section and emits intents (upload/remove/download).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Paperclip, X, Download } from '@lucide/vue'
import type { Attachment } from '@/services/attachments'

defineProps<{
  attachments: Attachment[]
  testId: string
  readOnly: boolean
  error?: string
}>()
const emit = defineEmits<{ upload: [File]; remove: [string]; download: [Attachment] }>()

const { t } = useI18n()
const fileInput = ref<HTMLInputElement | null>(null)

function onFilePicked(ev: Event): void {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) emit('upload', file)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <div class="mt-3 border-t border-dashed border-zinc-200 pt-2 dark:border-zinc-800">
    <ul v-if="attachments.length" class="space-y-1">
      <li
        v-for="a in attachments"
        :key="a.id"
        class="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400"
      >
        <Paperclip class="h-3 w-3 shrink-0 text-zinc-400" />
        <span class="truncate">{{ a.filename }}</span>
        <span class="shrink-0 text-zinc-400">{{ formatSize(a.size_bytes) }}</span>
        <button
          type="button"
          :data-test="`attach-download-${a.id}`"
          class="ml-auto flex h-6 items-center gap-1 rounded px-1.5 text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          :title="t('reports.attachments.download')"
          @click="emit('download', a)"
        >
          <Download class="h-3 w-3" />
        </button>
        <button
          v-if="!readOnly"
          type="button"
          :data-test="`attach-remove-${a.id}`"
          class="flex h-6 items-center rounded px-1.5 text-zinc-500 transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950"
          :title="t('reports.attachments.delete')"
          @click="emit('remove', a.id)"
        >
          <X class="h-3 w-3" />
        </button>
      </li>
    </ul>
    <div class="mt-1.5 flex items-center gap-2">
      <button
        v-if="!readOnly"
        type="button"
        :data-test="`attach-btn-${testId}`"
        class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
        @click="fileInput?.click()"
      >
        <Paperclip class="h-3.5 w-3.5" />
        {{ t('reports.attachments.upload') }}
      </button>
      <span v-if="error" :data-test="`attach-error-${testId}`" class="text-xs text-red-500">
        {{ error }}
      </span>
      <input
        ref="fileInput"
        :data-test="`attach-input-${testId}`"
        type="file"
        class="hidden"
        @change="onFilePicked"
      />
    </div>
  </div>
</template>
