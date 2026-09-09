import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import ReportContentPane from '@/views/evaluations/ReportContentPane.vue'
import type { GradableSection } from '@/services/evaluations'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function section(over: Partial<GradableSection> = {}): GradableSection {
  return {
    report_section_id: 's1',
    section_def_id: 'd1',
    name: 'Findings',
    description: 'What the team found',
    position: 0,
    field_type: 'rich_text',
    content: '<p>Hello</p>',
    content_plain: 'Hello',
    choice_values: null,
    grade_mode: 'numeric',
    grade_min: '0.00',
    grade_max: '10.00',
    grade_weight: '1.00',
    rubric_criteria: null,
    evaluation_criteria: null,
    grade: null,
    ...over,
  }
}

function mountPane(over: Partial<GradableSection> = {}) {
  return mount(ReportContentPane, {
    props: { section: section(over) },
    global: { plugins: [i18n] },
  })
}

describe('ReportContentPane', () => {
  it('renders sanitized rich_text content', () => {
    const w = mountPane({ content: '<p>Hello <strong>world</strong></p>' })
    const body = w.get('[data-test="content-body-s1"]')
    expect(body.html()).toContain('<strong>world</strong>')
    expect(body.text()).toContain('Hello world')
  })

  it('strips a script tag from untrusted section content', () => {
    const w = mountPane({
      content: '<p>safe</p><script>alert(1)</script><img src="x" onerror="alert(2)">',
    })
    const html = w.get('[data-test="content-body-s1"]').html()
    expect(html).toContain('safe')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onerror')
    // The image survives as a tag but loses a src outside the attachment endpoint.
    expect(html).not.toContain('src="x"')
  })

  it('renders choice_values as chips rather than HTML', () => {
    const w = mountPane({
      field_type: 'multi_choice',
      content: null,
      content_plain: null,
      choice_values: ['<b>TLP:RED</b>', 'Confirmed'],
    })
    const chips = w.findAll('[data-test^="content-chip-s1-"]')
    expect(chips).toHaveLength(2)
    // Escaped as text, not parsed: the markup is visible, not applied.
    expect(chips[0]!.text()).toBe('<b>TLP:RED</b>')
    expect(chips[0]!.html()).not.toContain('<b>')
    expect(w.find('[data-test="content-body-s1"]').exists()).toBe(false)
  })

  it('shows an empty-section placeholder when content is null', () => {
    const w = mountPane({ content: null, content_plain: null })
    expect(w.get('[data-test="content-empty-s1"]').text()).toBe(en.evaluations.emptySection)
    expect(w.find('[data-test="content-body-s1"]').exists()).toBe(false)
  })

  it('renders the character count in the pane header', () => {
    const w = mountPane({ content_plain: 'Hello' })
    expect(w.get('[data-test="content-chars-s1"]').text()).toContain('5')
  })
})
