import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en/common.json'
import CampaignDetail from '@/views/settings/CampaignDetail.vue'
import { useAuthStore } from '@/stores/auth'
import * as campaignsSvc from '@/services/campaigns'
import * as teamsSvc from '@/services/teams'
import * as evalSvc from '@/services/evaluations'
import { ApiError } from '@/services/http'
import type { Campaign } from '@/services/campaigns'
import type { Team, TeamEvaluatorSummary } from '@/services/teams'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { exerciseId: 'ex1', cid: 'c1' } }),
  useRouter: () => ({ push }),
  RouterLink: {
    props: ['to'],
    template: '<a :href="typeof to === \'string\' ? to : JSON.stringify(to)"><slot /></a>',
  },
}))

const CANDIDATES = [
  { user_id: 'u1', display_name: 'Eve', email: 'eve@x' },
  { user_id: 'u2', display_name: 'Ivan', email: 'ivan@x' },
]

function campaign(over: Partial<Campaign> = {}): Campaign {
  return {
    id: 'c1',
    exercise_id: 'ex1',
    name: 'Sitreps',
    description: null,
    report_count: 6,
    created_by: 'u1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function team(over: Partial<Team> = {}): Team {
  return { id: 't1', exercise_id: 'ex1', name: 'Alpha', team_type: 'blue', color: null, ...over }
}

function teamEvaluator(over: Partial<TeamEvaluatorSummary> = {}): TeamEvaluatorSummary {
  return {
    id: 'te1',
    team_id: 't1',
    evaluator_id: 'u1',
    display_name: 'Eve',
    email: 'eve@x',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function arrange(
  opts: {
    teams?: Team[]
    teamEvaluatorsByTeam?: Record<string, TeamEvaluatorSummary[]>
  } = {},
) {
  vi.spyOn(evalSvc, 'listEvaluatorCandidates').mockResolvedValue(CANDIDATES)
  vi.spyOn(campaignsSvc, 'getCampaign').mockResolvedValue(campaign())
  vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue(opts.teams ?? [team()])
  vi.spyOn(teamsSvc, 'listTeamEvaluators').mockImplementation(
    async (_t, _e, teamId) => (opts.teamEvaluatorsByTeam ?? {})[teamId] ?? [],
  )
}

async function mountPage() {
  const wrapper = mount(CampaignDetail, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('CampaignDetail.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    push.mockClear()
    useAuthStore().setSession({
      access_token: 'tok',
      token_type: 'bearer',
      user: { id: 'ga', email: 'a', display_name: 'Ada', avatar_url: null, is_global_admin: true },
    })
  })

  it('loads the campaign name and every team with its own evaluators — no separate campaign-level panel', async () => {
    arrange({
      teams: [team({ id: 't1', name: 'Alpha' }), team({ id: 't2', name: 'Bravo' })],
      teamEvaluatorsByTeam: { t1: [teamEvaluator({ id: 'te1', team_id: 't1' })] },
    })
    const wrapper = await mountPage()

    expect(wrapper.get('[data-test="campaign-detail-name"]').text()).toContain('Sitreps')
    expect(wrapper.get('[data-test="team-heading-t1"]').text()).toContain('Alpha')
    expect(wrapper.get('[data-test="team-heading-t2"]').text()).toContain('Bravo')
    expect(wrapper.get('[data-test="assign-row-te1"]').text()).toContain('Eve')
    // The campaign-level picker is gone entirely — no un-prefixed "assign-pick" left.
    expect(wrapper.find('[data-test="assign-pick"]').exists()).toBe(false)
  })

  it('mounts one EvaluatorAssignmentPanel per team with distinct picker ids', async () => {
    arrange({ teams: [team({ id: 't1' }), team({ id: 't2' })] })
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="assign-pick-team-t1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="assign-pick-team-t2"]').exists()).toBe(true)
  })

  // The whole point of the change: assigning someone to a team from a campaign's own detail
  // page satisfies BOTH halves of the team_evaluator ∩ campaign_evaluator intersection in one
  // click — there is no separate campaign-level step any more.
  it('assigning a team evaluator also writes the campaign_evaluator row for this campaign', async () => {
    arrange({ teams: [team({ id: 't1' })] })
    const addTeam = vi.spyOn(teamsSvc, 'addTeamEvaluator').mockResolvedValue(teamEvaluator())
    const addCampaign = vi
      .spyOn(campaignsSvc, 'addCampaignEvaluator')
      .mockResolvedValue({} as never)
    const wrapper = await mountPage()
    vi.mocked(teamsSvc.listTeamEvaluators).mockResolvedValue([teamEvaluator()])

    await wrapper.get('[data-test="assign-pick-team-t1"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit-team-t1"]').trigger('click')
    await flushPromises()

    expect(addTeam).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u1')
    expect(addCampaign).toHaveBeenCalledWith('tok', 'ex1', 'c1', 'u1')
    expect(wrapper.get('[data-test="assign-row-te1"]').text()).toContain('Eve')
  })

  // Assigning the same evaluator to a second team in the same campaign re-attempts the
  // campaign_evaluator write — the backend 409s ("already assigned"), which is expected and
  // must not surface as an error; the team assignment itself still succeeds.
  it('treats a 409 from addCampaignEvaluator as benign — evaluator already covers this campaign', async () => {
    arrange({ teams: [team({ id: 't1' }), team({ id: 't2' })] })
    vi.spyOn(teamsSvc, 'addTeamEvaluator').mockResolvedValue(
      teamEvaluator({ id: 'te2', team_id: 't2' }),
    )
    vi.spyOn(campaignsSvc, 'addCampaignEvaluator').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'already assigned', [], undefined, 409),
    )
    const wrapper = await mountPage()
    vi.mocked(teamsSvc.listTeamEvaluators).mockImplementation(async (_t, _e, teamId) =>
      teamId === 't2' ? [teamEvaluator({ id: 'te2', team_id: 't2' })] : [],
    )

    await wrapper.get('[data-test="assign-pick-team-t2"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit-team-t2"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="assign-row-te2"]').text()).toContain('Eve')
    expect(wrapper.find('[data-test="assign-error-team-t2"]').exists()).toBe(false)
  })

  it('surfaces a real (non-409) failure from addCampaignEvaluator as an error', async () => {
    arrange({ teams: [team({ id: 't1' })] })
    vi.spyOn(teamsSvc, 'addTeamEvaluator').mockResolvedValue(teamEvaluator())
    vi.spyOn(campaignsSvc, 'addCampaignEvaluator').mockRejectedValue(
      new ApiError('HTTP_ERROR', 'server exploded', [], undefined, 500),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-test="assign-pick-team-t1"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit-team-t1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="assign-error-team-t1"]').exists()).toBe(true)
  })

  it('removing for a specific team calls removeTeamEvaluator for that team', async () => {
    arrange({
      teams: [team({ id: 't1' })],
      teamEvaluatorsByTeam: { t1: [teamEvaluator({ id: 'te1', team_id: 't1' })] },
    })
    const remove = vi.spyOn(teamsSvc, 'removeTeamEvaluator').mockResolvedValue(undefined)
    const wrapper = await mountPage()
    vi.mocked(teamsSvc.listTeamEvaluators).mockResolvedValue([])

    await wrapper.get('[data-test="assign-remove-te1"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u1')
    expect(wrapper.find('[data-test="assign-row-te1"]').exists()).toBe(false)
  })

  it('renames the campaign via updateCampaign and reflects the new name', async () => {
    arrange()
    const update = vi
      .spyOn(campaignsSvc, 'updateCampaign')
      .mockResolvedValue(campaign({ name: 'Renamed' }))
    const wrapper = await mountPage()

    await wrapper.get('[data-test="edit-campaign-name"]').trigger('click')
    await wrapper.get('[data-test="campaign-name-input"]').setValue('Renamed')
    await wrapper.get('[data-test="save-campaign-name"]').trigger('click')
    await flushPromises()

    expect(update).toHaveBeenCalledWith('tok', 'ex1', 'c1', { name: 'Renamed' })
    expect(wrapper.get('[data-test="campaign-detail-name"]').text()).toContain('Renamed')
    expect(wrapper.find('[data-test="campaign-name-input"]').exists()).toBe(false)
  })

  it('cancelling the rename discards the draft without calling updateCampaign', async () => {
    arrange()
    const update = vi.spyOn(campaignsSvc, 'updateCampaign')
    const wrapper = await mountPage()

    await wrapper.get('[data-test="edit-campaign-name"]').trigger('click')
    await wrapper.get('[data-test="campaign-name-input"]').setValue('Whatever')
    await wrapper.get('[data-test="cancel-campaign-name"]').trigger('click')

    expect(update).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="campaign-name-input"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="campaign-detail-name"]').text()).toContain('Sitreps')
  })

  it('surfaces a rename error without leaving edit mode', async () => {
    arrange()
    vi.spyOn(campaignsSvc, 'updateCampaign').mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()

    await wrapper.get('[data-test="edit-campaign-name"]').trigger('click')
    await wrapper.get('[data-test="campaign-name-input"]').setValue('Renamed')
    await wrapper.get('[data-test="save-campaign-name"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="campaign-name-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="campaign-name-input"]').exists()).toBe(true)
  })

  it('shows a load error when the campaign fails to load', async () => {
    arrange()
    vi.spyOn(campaignsSvc, 'getCampaign').mockRejectedValue(new Error('boom'))
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="campaign-detail-load-error"]').exists()).toBe(true)
  })
})
