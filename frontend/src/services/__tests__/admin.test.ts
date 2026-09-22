import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as exercises from '@/services/exercises'
import * as teams from '@/services/teams'
import * as teamTypes from '@/services/teamTypes'
import * as exerciseRoles from '@/services/exerciseRoles'
import * as users from '@/services/users'

function env(status: number, data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('admin service layer', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('createExercise POSTs to /exercises', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 'e1', name: 'Autumn' }))
    vi.stubGlobal('fetch', fetchMock)
    const out = await exercises.createExercise('tok', { name: 'Autumn' })
    expect(out.id).toBe('e1')
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises')
    expect(fetchMock.mock.calls[0]![1].method).toBe('POST')
  })

  it('archiveExercise DELETEs and returns the archived exercise body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, { id: 'e1', status: 'archived' }))
    vi.stubGlobal('fetch', fetchMock)
    const out = await exercises.archiveExercise('tok', 'e1')
    expect(out.status).toBe('archived')
    expect(fetchMock.mock.calls[0]![1].method).toBe('DELETE')
  })

  it('createTeam POSTs the team fields to the exercise-scoped path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 't1', name: 'Alpha' }))
    vi.stubGlobal('fetch', fetchMock)
    await teams.createTeam('tok', 'e1', { name: 'Alpha', team_type: 'blue' })
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/e1/teams')
  })

  it('addTeamMember POSTs the user_id to the members path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 'm1', user_id: 'u1' }))
    vi.stubGlobal('fetch', fetchMock)
    await teams.addTeamMember('tok', 'e1', 't1', 'u1')
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/e1/teams/t1/members')
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual({ user_id: 'u1' })
  })

  it('createTeamType POSTs to the team-types path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 'tt1', type_key: 'blue' }))
    vi.stubGlobal('fetch', fetchMock)
    await teamTypes.createTeamType('tok', 'e1', { type_key: 'blue', display_label: 'Blue Team' })
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/exercises/e1/team-types')
  })

  it('grantExerciseRole POSTs user_id and role_key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(201, { id: 'r1' }))
    vi.stubGlobal('fetch', fetchMock)
    await exerciseRoles.grantExerciseRole('tok', 'e1', 'u1', 'evaluator')
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual({
      user_id: 'u1',
      role_key: 'evaluator',
    })
  })

  it('searchUsers GETs with the query string encoded', async () => {
    const fetchMock = vi.fn().mockResolvedValue(env(200, [{ id: 'u1', display_name: 'Eve' }]))
    vi.stubGlobal('fetch', fetchMock)
    await users.searchUsers('tok', 'a b')
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/users?q=a%20b')
  })
})
