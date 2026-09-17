import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import PaneHeader from '@/views/evaluations/PaneHeader.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

describe('PaneHeader.vue', () => {
  it('renders the previous report name, team, and its overall grade', () => {
    const wrapper = mount(PaneHeader, {
      props: {
        label: 'Previous',
        reportName: 'Day 1 SITREP',
        teamName: 'Blue Team Alpha',
        overallGrade: '7.80',
        gradeMax: '10',
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Day 1 SITREP')
    expect(wrapper.text()).toContain('Blue Team Alpha')
    expect(wrapper.find('[data-test="pane-grade"]').text()).toBe('7.80 / 10')
  })

  it("renders an em dash for the current report's not-yet-computed overall grade", () => {
    const wrapper = mount(PaneHeader, {
      props: {
        label: 'Current',
        reportName: 'Day 2 SITREP',
        teamName: 'Blue Team Alpha',
        overallGrade: null,
        gradeMax: '10',
        isCurrent: true,
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[data-test="pane-grade"]').text()).toBe('— / 10')
  })

  it('labels the current pane as the one being graded', () => {
    const withCurrent = mount(PaneHeader, {
      props: {
        label: 'Current',
        reportName: 'Day 2 SITREP',
        teamName: 'Blue Team Alpha',
        overallGrade: null,
        gradeMax: '10',
        isCurrent: true,
      },
      global: { plugins: [i18n] },
    })
    const withoutCurrent = mount(PaneHeader, {
      props: {
        label: 'Previous',
        reportName: 'Day 1 SITREP',
        teamName: 'Blue Team Alpha',
        overallGrade: '7.80',
        gradeMax: '10',
      },
      global: { plugins: [i18n] },
    })
    expect(withCurrent.find('[data-test="pane-being-graded"]').exists()).toBe(true)
    expect(withoutCurrent.find('[data-test="pane-being-graded"]').exists()).toBe(false)
  })
})
