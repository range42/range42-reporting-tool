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
import type { Campaign, CampaignEvaluatorSummary } from '@/services/campaigns'
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

function campaignEvaluator(over: Partial<CampaignEvaluatorSummary> = {}): CampaignEvaluatorSummary {
  return {
    id: 'ce1',
    campaign_id: 'c1',
    evaluator_id: 'u1',
    display_name: 'Eve',
    email: 'eve@x',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  }
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
    campaignEvaluators?: CampaignEvaluatorSummary[]
    teamEvaluatorsByTeam?: Record<string, TeamEvaluatorSummary[]>
  } = {},
) {
  vi.spyOn(evalSvc, 'listEvaluatorCandidates').mockResolvedValue(CANDIDATES)
  vi.spyOn(campaignsSvc, 'getCampaign').mockResolvedValue(campaign())
  vi.spyOn(teamsSvc, 'listTeams').mockResolvedValue(opts.teams ?? [team()])
  vi.spyOn(campaignsSvc, 'listCampaignEvaluators').mockResolvedValue(opts.campaignEvaluators ?? [])
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

  it('loads the campaign name, campaign evaluators, and every team with its own evaluators', async () => {
    arrange({
      teams: [team({ id: 't1', name: 'Alpha' }), team({ id: 't2', name: 'Bravo' })],
      campaignEvaluators: [campaignEvaluator()],
      teamEvaluatorsByTeam: { t1: [teamEvaluator({ id: 'te1', team_id: 't1' })] },
    })
    const wrapper = await mountPage()

    expect(wrapper.get('[data-test="campaign-detail-name"]').text()).toContain('Sitreps')
    expect(wrapper.get('[data-test="assign-row-ce1"]').text()).toContain('Eve')
    expect(wrapper.get('[data-test="team-heading-t1"]').text()).toContain('Alpha')
    expect(wrapper.get('[data-test="team-heading-t2"]').text()).toContain('Bravo')
    expect(wrapper.get('[data-test="assign-row-te1"]').text()).toContain('Eve')
  })

  it('mounts one EvaluatorAssignmentPanel per team with distinct picker ids', async () => {
    arrange({ teams: [team({ id: 't1' }), team({ id: 't2' })] })
    const wrapper = await mountPage()

    expect(wrapper.find('[data-test="assign-pick-team-t1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="assign-pick-team-t2"]').exists()).toBe(true)
  })

  it('assigning at the campaign level calls addCampaignEvaluator and reloads', async () => {
    arrange()
    const add = vi
      .spyOn(campaignsSvc, 'addCampaignEvaluator')
      .mockResolvedValue(campaignEvaluator())
    const wrapper = await mountPage()
    vi.mocked(campaignsSvc.listCampaignEvaluators).mockResolvedValue([campaignEvaluator()])

    await wrapper.get('[data-test="assign-pick"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit"]').trigger('click')
    await flushPromises()

    expect(add).toHaveBeenCalledWith('tok', 'ex1', 'c1', 'u1')
    expect(wrapper.get('[data-test="assign-row-ce1"]').text()).toContain('Eve')
  })

  it('removing at the campaign level calls removeCampaignEvaluator and reloads', async () => {
    arrange({ campaignEvaluators: [campaignEvaluator()] })
    const remove = vi.spyOn(campaignsSvc, 'removeCampaignEvaluator').mockResolvedValue(undefined)
    const wrapper = await mountPage()
    vi.mocked(campaignsSvc.listCampaignEvaluators).mockResolvedValue([])

    await wrapper.get('[data-test="assign-remove-ce1"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('tok', 'ex1', 'c1', 'u1')
    expect(wrapper.find('[data-test="assign-row-ce1"]').exists()).toBe(false)
  })

  it('assigning for a specific team calls addTeamEvaluator for that team only and reloads only its rows', async () => {
    arrange({ teams: [team({ id: 't1' }), team({ id: 't2' })] })
    const add = vi.spyOn(teamsSvc, 'addTeamEvaluator').mockResolvedValue(teamEvaluator())
    const wrapper = await mountPage()
    vi.mocked(teamsSvc.listTeamEvaluators).mockImplementation(async (_t, _e, teamId) =>
      teamId === 't1' ? [teamEvaluator({ id: 'te1', team_id: 't1' })] : [],
    )

    await wrapper.get('[data-test="assign-pick-team-t1"]').setValue('u1')
    await wrapper.get('[data-test="assign-submit-team-t1"]').trigger('click')
    await flushPromises()

    expect(add).toHaveBeenCalledWith('tok', 'ex1', 't1', 'u1')
    expect(wrapper.get('[data-test="assign-row-te1"]').text()).toContain('Eve')
    expect(wrapper.find('[data-test="assign-pick-team-t2"]').exists()).toBe(true)
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
