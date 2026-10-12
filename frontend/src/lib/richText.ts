import { generateHTML, generateJSON, type AnyExtension } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { Table } from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableHeader from '@tiptap/extension-table-header'
import TableCell from '@tiptap/extension-table-cell'

/** The report editor's schema; `image` lets the editor swap in its authenticated node view. */
export function richTextExtensions(image: AnyExtension = Image): AnyExtension[] {
  return [
    StarterKit,
    image,
    Table.configure({ resizable: false }),
    TableRow,
    TableHeader,
    TableCell,
  ]
}

/** `html` re-serialized through the editor schema, so equal documents compare equal as strings. */
export function normalizeRichText(html: string): string {
  const extensions = richTextExtensions()
  return generateHTML(generateJSON(html, extensions), extensions)
}
