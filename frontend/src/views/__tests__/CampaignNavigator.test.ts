import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import CampaignNavigator from '@/views/evaluations/CampaignNavigator.vue'
import type { TimelineEntry } from '@/services/campaigns'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function entry(over: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    report_id: 'r1',
    name: 'Day 1',
    status: 'submitted',
    team_id: 't1',
    team_name: 'Blue',
    submitted_at: '2026-09-01T09:00:00Z',
    due_at: null,
    created_at: '2026-09-01T08:00:00Z',
    ...over,
  }
}

function mountNav(entries: TimelineEntry[], currentReportId: string) {
  return mount(CampaignNavigator, {
    props: { entries, currentReportId },
    global: { plugins: [i18n] },
  })
}

describe('CampaignNavigator.vue', () => {
  it('renders one pill per campaign entry in timeline order', () => {
    const entries = [
      entry({ report_id: 'r1' }),
      entry({ report_id: 'r2' }),
      entry({ report_id: 'r3' }),
    ]
    const wrapper = mountNav(entries, 'r2')
    const pills = wrapper.findAll('button')
    expect(pills.map((p) => p.attributes('data-test'))).toEqual([
      'nav-pill-r1',
      'nav-pill-r2',
      'nav-pill-r3',
    ])
  })

  it("marks the current report's pill with aria-current", () => {
    const entries = [entry({ report_id: 'r1' }), entry({ report_id: 'r2' })]
    const wrapper = mountNav(entries, 'r2')
    expect(wrapper.find('[data-test="nav-pill-r1"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.find('[data-test="nav-pill-r2"]').attributes('aria-current')).toBe('true')
  })

  it('distinguishes evaluated, submitted, and not-yet-submitted entries', () => {
    const entries = [
      entry({ report_id: 'r1', status: 'evaluated' }),
      entry({ report_id: 'r2', status: 'submitted' }),
      entry({ report_id: 'r3', status: 'draft' }),
    ]
    const wrapper = mountNav(entries, 'none')
    expect(wrapper.find('[data-test="nav-pill-r1"]').attributes('data-status')).toBe('evaluated')
    expect(wrapper.find('[data-test="nav-pill-r2"]').attributes('data-status')).toBe('submitted')
    expect(wrapper.find('[data-test="nav-pill-r3"]').attributes('data-status')).toBe('draft')
    // Evaluated gets a visibly different class from a not-yet-evaluated entry.
    const evaluatedClass = wrapper.find('[data-test="nav-pill-r1"]').classes().join(' ')
    const draftClass = wrapper.find('[data-test="nav-pill-r3"]').classes().join(' ')
    expect(evaluatedClass).not.toBe(draftClass)
  })

  it('emits select with the report id when a pill is activated', async () => {
    const entries = [entry({ report_id: 'r1' }), entry({ report_id: 'r2' })]
    const wrapper = mountNav(entries, 'r1')
    await wrapper.find('[data-test="nav-pill-r2"]').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['r2']])
  })

  it('renders pills as buttons reachable by keyboard', () => {
    const entries = [entry({ report_id: 'r1' }), entry({ report_id: 'r2' })]
    const wrapper = mountNav(entries, 'r1')
    const pills = wrapper.findAll('[data-test^="nav-pill-"]')
    expect(pills).toHaveLength(2)
    for (const pill of pills) expect(pill.element.tagName).toBe('BUTTON')
  })
})
