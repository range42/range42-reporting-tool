<script setup lang="ts">
/**
 * Rich-text field. TipTap (StarterKit) is the production editor. ProseMirror
 * does not run under jsdom, so alongside the editor we render a visually-hidden
 * <textarea> mirror bound to the same v-model — that textarea (data-test
 * "content-{testId}") is the deterministic surface component tests drive.
 * Tests mock @tiptap/vue-3 so no real ProseMirror DOM is required.
 *
 * Inline images: the document model keeps the canonical
 * `/api/v1/.../attachments/{id}/download` src (the only form the shared
 * sanitize policy allows). The API is bearer-authenticated, so a plain <img>
 * cannot load it — the AuthedImage node view fetches the blob with the token
 * and points the rendered element at an object URL instead.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { Table } from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableHeader from '@tiptap/extension-table-header'
import TableCell from '@tiptap/extension-table-cell'
import { ImagePlus, Table2, Rows3, Columns3, Trash2 } from '@lucide/vue'
import { resolveAttachmentObjectUrl } from '@/services/attachments'
import { IMG_SRC_PATTERN } from '@/services/sanitize'

const props = defineProps<{
  modelValue: string
  testId: string
  disabled?: boolean
  /** Upload the picked file; resolves to the canonical attachment download URL. */
  imageUpload?: (file: File) => Promise<string>
  /** Bearer token used to resolve inline-image blobs. */
  token?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const { t } = useI18n()

const AuthedImage = Image.extend({
  addNodeView() {
    return ({ node }) => {
      const img = document.createElement('img')
      img.alt = (node.attrs.alt as string | null) ?? ''
      const src = (node.attrs.src as string | null) ?? ''
      if (IMG_SRC_PATTERN.test(src)) {
        resolveAttachmentObjectUrl(src, props.token ?? '')
          .then((url) => {
            img.src = url
          })
          .catch(() => {
            img.alt = img.alt || 'image unavailable'
          })
      } else if (src) {
        img.src = src
      }
      return { dom: img }
    }
  },
})

const editor = useEditor({
  content: props.modelValue,
  editable: !props.disabled,
  extensions: [
    StarterKit,
    AuthedImage,
    Table.configure({ resizable: false }),
    TableRow,
    TableHeader,
    TableCell,
  ],
  onUpdate: ({ editor }) => emit('update:modelValue', editor.getHTML()),
})

watch(
  () => props.modelValue,
  (v) => {
    const e = editor.value
    if (e && e.getHTML() !== v) e.commands.setContent(v, { emitUpdate: false })
  },
)
watch(
  () => props.disabled,
  (d) => editor.value?.setEditable(!d),
)

onBeforeUnmount(() => editor.value?.destroy())

function onTextarea(ev: Event): void {
  emit('update:modelValue', (ev.target as HTMLTextAreaElement).value)
}

const imageInput = ref<HTMLInputElement | null>(null)
const imageError = ref(false)

async function onImagePicked(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.imageUpload) return
  imageError.value = false
  try {
    const src = await props.imageUpload(file)
    editor.value?.chain().focus().setImage({ src, alt: file.name }).run()
  } catch {
    imageError.value = true
  }
}

function onInsertTable(): void {
  editor.value?.chain().focus().insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run()
}
function onAddRow(): void {
  editor.value?.chain().focus().addRowAfter().run()
}
function onAddColumn(): void {
  editor.value?.chain().focus().addColumnAfter().run()
}
function onDeleteRow(): void {
  editor.value?.chain().focus().deleteRow().run()
}
function onDeleteColumn(): void {
  editor.value?.chain().focus().deleteColumn().run()
}

const isInTable = computed(() => editor.value?.isActive('table') ?? false)
</script>

<template>
  <div>
    <div
      class="min-h-[7rem] rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm transition focus-within:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900"
    >
      <EditorContent :editor="editor" />
    </div>
    <div v-if="!disabled" class="mt-1.5 flex items-center gap-2">
      <button
        v-if="imageUpload"
        type="button"
        :data-test="`img-btn-${testId}`"
        class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
        @click="imageInput?.click()"
      >
        <ImagePlus class="h-3.5 w-3.5" />
        {{ t('reports.attachments.insertImage') }}
      </button>
      <button
        type="button"
        :data-test="`table-btn-${testId}`"
        class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
        @click="onInsertTable"
      >
        <Table2 class="h-3.5 w-3.5" />
        {{ t('reports.insertTable') }}
      </button>
      <template v-if="isInTable">
        <button
          type="button"
          :data-test="`table-add-row-${testId}`"
          class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          @click="onAddRow"
        >
          <Rows3 class="h-3.5 w-3.5" />
          {{ t('reports.addRow') }}
        </button>
        <button
          type="button"
          :data-test="`table-add-column-${testId}`"
          class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          @click="onAddColumn"
        >
          <Columns3 class="h-3.5 w-3.5" />
          {{ t('reports.addColumn') }}
        </button>
        <button
          type="button"
          :data-test="`table-delete-row-${testId}`"
          class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          @click="onDeleteRow"
        >
          <Trash2 class="h-3.5 w-3.5" />
          {{ t('reports.deleteRow') }}
        </button>
        <button
          type="button"
          :data-test="`table-delete-column-${testId}`"
          class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          @click="onDeleteColumn"
        >
          <Trash2 class="h-3.5 w-3.5" />
          {{ t('reports.deleteColumn') }}
        </button>
      </template>
      <span v-if="imageError" :data-test="`img-error-${testId}`" class="text-xs text-red-500">
        {{ t('reports.attachments.uploadFailed') }}
      </span>
      <input
        v-if="imageUpload"
        ref="imageInput"
        :data-test="`img-input-${testId}`"
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        class="hidden"
        @change="onImagePicked"
      />
    </div>
    <textarea
      :data-test="`content-${testId}`"
      class="sr-only"
      :value="modelValue"
      :disabled="disabled"
      aria-hidden="true"
      tabindex="-1"
      @input="onTextarea"
    />
  </div>
</template>

<style scoped>
/* Mirrors .prose-rt (main.css) — the evaluator's read-only rendering — so the writer's
   live editor previews headings/lists/tables the same way they'll actually be shown. */
:deep(.tiptap p) {
  margin: 0.6em 0;
  line-height: 1.65;
}
:deep(.tiptap ul) {
  list-style: disc;
  padding-left: 1.3em;
  margin: 0.6em 0;
}
:deep(.tiptap ol) {
  list-style: decimal;
  padding-left: 1.3em;
  margin: 0.6em 0;
}
:deep(.tiptap li) {
  margin: 0.2em 0;
}
:deep(.tiptap strong) {
  font-weight: 600;
  color: inherit;
}
:deep(.tiptap code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
  background: color-mix(in oklab, var(--rt-accent) 10%, transparent);
  color: var(--rt-accent);
  padding: 0.08em 0.35em;
  border-radius: 3px;
}
:deep(.tiptap h1),
:deep(.tiptap h2),
:deep(.tiptap h3) {
  font-weight: 600;
  line-height: 1.25;
  margin: 1.2em 0 0.4em;
}
:deep(.tiptap h1) {
  font-size: 1.35rem;
}
:deep(.tiptap h2) {
  font-size: 1.15rem;
}
:deep(.tiptap h3) {
  font-size: 1rem;
}
:deep(.tiptap blockquote) {
  border-left: 2px solid var(--rt-border);
  padding-left: 0.9em;
  margin: 0.6em 0;
  color: var(--rt-fg-muted);
}
:deep(.tiptap table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
}
:deep(.tiptap th),
:deep(.tiptap td) {
  border: 1px solid var(--rt-border);
  padding: 0.35em 0.6em;
  text-align: left;
  vertical-align: top;
}
:deep(.tiptap th) {
  font-weight: 600;
  background: color-mix(in oklab, var(--rt-fg) 4%, transparent);
}
</style>
