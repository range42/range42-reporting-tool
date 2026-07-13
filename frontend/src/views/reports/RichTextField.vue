<script setup lang="ts">
/**
 * Rich-text field. TipTap (StarterKit) is the production editor. ProseMirror
 * does not run under jsdom, so alongside the editor we render a visually-hidden
 * <textarea> mirror bound to the same v-model — that textarea (data-test
 * "content-{testId}") is the deterministic surface component tests drive.
 * Tests mock @tiptap/vue-3 so no real ProseMirror DOM is required.
 */
import { onBeforeUnmount, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'

const props = defineProps<{ modelValue: string; testId: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const editor = useEditor({
  content: props.modelValue,
  editable: !props.disabled,
  extensions: [StarterKit],
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
</script>

<template>
  <div>
    <div
      class="min-h-[7rem] rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm transition focus-within:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900"
    >
      <EditorContent :editor="editor" />
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
