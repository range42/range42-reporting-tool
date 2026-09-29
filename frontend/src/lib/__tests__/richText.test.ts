import { describe, expect, it } from 'vitest'
import { Editor } from '@tiptap/vue-3'
import { normalizeRichText, richTextExtensions } from '@/lib/richText'

const SERVER_TABLE =
  '<table><thead><tr><th>Named Threat</th><th>Detection</th></tr></thead>' +
  '<tbody><tr><td></td><td></td></tr></tbody></table>'

function editorHtml(content: string): string {
  const editor = new Editor({ content, extensions: richTextExtensions() })
  const html = editor.getHTML()
  editor.destroy()
  return html
}

describe('normalizeRichText', () => {
  it('maps server table HTML and the editor serialization of it to the same string', () => {
    const fromEditor = editorHtml(SERVER_TABLE)
    expect(fromEditor).not.toBe(SERVER_TABLE)
    expect(normalizeRichText(SERVER_TABLE)).toBe(normalizeRichText(fromEditor))
  })

  it('treats empty content and an empty paragraph as the same document', () => {
    expect(normalizeRichText('')).toBe(normalizeRichText('<p></p>'))
  })

  it('keeps different documents different', () => {
    expect(normalizeRichText('<p>a</p>')).not.toBe(normalizeRichText('<p>b</p>'))
  })
})
