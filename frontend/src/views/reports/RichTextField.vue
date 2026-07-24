<script setup lang="ts">
/**
 * Rich-text field. TipTap (StarterKit) is the production editor. ProseMirror
 * does not run under jsdom, so alongside the editor we render a visually-hidden
 * <textarea> mirror bound to the same v-model — that textarea (data-test
 * "content-{testId}") is the deterministic surface component tests drive.
 * Tests mock @tiptap/vue-3 so no real ProseMirror DOM is required.
 *
 * Inline images (WP3 S9): the document model keeps the canonical
 * `/api/v1/.../attachments/{id}/download` src (the only form the shared
 * sanitize policy allows). The API is bearer-authenticated, so a plain <img>
 * cannot load it — the AuthedImage node view fetches the blob with the token
 * and points the rendered element at an object URL instead.
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { ImagePlus } from '@lucide/vue'
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
  extensions: [StarterKit, AuthedImage],
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
</script>

<template>
  <div>
    <div
      class="min-h-[7rem] rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm transition focus-within:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900"
    >
      <EditorContent :editor="editor" />
    </div>
    <div v-if="imageUpload && !disabled" class="mt-1.5 flex items-center gap-2">
      <button
        type="button"
        :data-test="`img-btn-${testId}`"
        class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
        @click="imageInput?.click()"
      >
        <ImagePlus class="h-3.5 w-3.5" />
        {{ t('reports.attachments.insertImage') }}
      </button>
      <span v-if="imageError" :data-test="`img-error-${testId}`" class="text-xs text-red-500">
        {{ t('reports.attachments.uploadFailed') }}
      </span>
      <input
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
