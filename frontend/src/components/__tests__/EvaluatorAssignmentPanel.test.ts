import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import EvaluatorAssignmentPanel from '@/components/EvaluatorAssignmentPanel.vue'

const CANDIDATES = [
  { user_id: 'u1', display_name: 'Eve', email: 'eve@x' },
  { user_id: 'u2', display_name: 'Ivan', email: 'ivan@x' },
]

const LABELS = {
  addHeading: 'Add',
  noCandidatesText: 'No candidates',
  pickLabel: 'Pick one',
  assignActionText: 'Assign',
  currentHeading: 'Current',
  nobodyText: 'Nobody',
  removeActionText: 'Remove',
}

describe('EvaluatorAssignmentPanel.vue', () => {
  it('emits assign with the picked candidate id and clears the picker', async () => {
    const wrapper = mount(EvaluatorAssignmentPanel, {
      props: { rows: [], candidates: CANDIDATES, ...LABELS },
    })
    await wrapper.get('[data-test="assign-pick"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit"]').trigger('click')

    expect(wrapper.emitted('assign')).toEqual([['u1']])
    expect((wrapper.get('[data-test="assign-pick"]').element as HTMLSelectElement).value).toBe('')
  })

  it('emits remove with the row evaluator id', async () => {
    const wrapper = mount(EvaluatorAssignmentPanel, {
      props: {
        rows: [{ id: 'r1', evaluator_id: 'u1', display_name: 'Eve', email: 'eve@x' }],
        candidates: CANDIDATES,
        ...LABELS,
      },
    })
    await wrapper.get('[data-test="assign-remove-r1"]').trigger('click')
    expect(wrapper.emitted('remove')).toEqual([['u1']])
  })

  it('excludes already-assigned candidates from the picker', () => {
    const wrapper = mount(EvaluatorAssignmentPanel, {
      props: {
        rows: [{ id: 'r1', evaluator_id: 'u1', display_name: 'Eve', email: 'eve@x' }],
        candidates: CANDIDATES,
        ...LABELS,
      },
    })
    const options = wrapper.findAll('[data-test="assign-pick"] option').map((o) => o.text())
    expect(options.some((o) => o.includes('Ivan'))).toBe(true)
    expect(options.some((o) => o.includes('Eve'))).toBe(false)
  })

  it('uses plain ids with no testPrefix, matching the original single-instance screens', () => {
    const wrapper = mount(EvaluatorAssignmentPanel, {
      props: { rows: [], candidates: [], ...LABELS },
    })
    expect(wrapper.find('[data-test="assign-no-candidates"]').exists()).toBe(true)
  })

  it('disambiguates ids with testPrefix so multiple instances can coexist on one page', () => {
    const a = mount(EvaluatorAssignmentPanel, {
      props: { rows: [], candidates: CANDIDATES, testPrefix: 'team-t1', ...LABELS },
    })
    const b = mount(EvaluatorAssignmentPanel, {
      props: { rows: [], candidates: CANDIDATES, testPrefix: 'team-t2', ...LABELS },
    })
    expect(a.find('[data-test="assign-pick-team-t1"]').exists()).toBe(true)
    expect(b.find('[data-test="assign-pick-team-t2"]').exists()).toBe(true)
    expect(a.find('[data-test="assign-pick"]').exists()).toBe(false)
  })

  it('shows the assign error text when given one', () => {
    const wrapper = mount(EvaluatorAssignmentPanel, {
      props: { rows: [], candidates: CANDIDATES, assignError: 'boom', ...LABELS },
    })
    expect(wrapper.find('[data-test="assign-error"]').text()).toBe('boom')
  })

  it('disables the assign button while assigning', () => {
    const wrapper = mount(EvaluatorAssignmentPanel, {
      props: { rows: [], candidates: CANDIDATES, assigning: true, ...LABELS },
    })
    expect(wrapper.get('[data-test="assign-submit"]').attributes('disabled')).toBeDefined()
  })
})
