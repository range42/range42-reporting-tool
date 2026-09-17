import { chromium, request } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const BASE = 'http://localhost:5173'
const API = 'http://localhost:8000'
const STORAGE_STATE = `${__dirname}/.auth/admin-storage.json`
const FIXTURE_FILE = `${__dirname}/.auth/fixture.json`

/**
 * Logs the seeded `admin@range42.local` persona in through the real Dex SSO flow (a browser,
 * not a raw HTTP shortcut — this IS the login journey a real evaluator would take), then uses
 * that admin's bearer token to provision everything the spec needs: a template, three
 * team-pairs (two report cycles each, or one solo report) and a campaign tying them together.
 *
 * The admin is used as the evaluator throughout. `is_global_admin` bypasses every permission
 * and team-scoping check server-side, so this is a legitimate way to exercise the FEATURE's own
 * logic without re-deriving the separate REPORTS_READ_ASSIGNED scoping already covered by the
 * backend pytest suite.
 */
async function loginAndSaveStorage(): Promise<string> {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  await page.goto(`${BASE}/login`)
  await page.getByRole('button', { name: /sign in with sso/i }).click()
  await page.fill('#login', 'admin@range42.local')
  await page.fill('#password', 'changeme')
  await page.click('#submit-login')
  await page.waitForURL('**/exercises**', { timeout: 15000 })
  const token = await page.evaluate(() => localStorage.getItem('rt_token'))
  if (!token) throw new Error('admin login did not produce a token')
  await page.context().storageState({ path: STORAGE_STATE })
  await browser.close()
  return token
}

type JsonRecord = Record<string, unknown>

interface Api {
  get: (path: string) => Promise<JsonRecord>
  post: (path: string, body?: unknown) => Promise<JsonRecord>
  patch: (path: string, body?: unknown) => Promise<JsonRecord>
  put: (path: string, body?: unknown) => Promise<JsonRecord>
}

function makeApi(ctx: Awaited<ReturnType<typeof request.newContext>>, token: string): Api {
  const headers = { Authorization: `Bearer ${token}` }
  async function unwrap(resp: Awaited<ReturnType<typeof ctx.post>>): Promise<JsonRecord> {
    if (!resp.ok()) throw new Error(`${resp.url()} -> ${resp.status()}: ${await resp.text()}`)
    const body = (await resp.json()) as { data: JsonRecord }
    return body.data
  }
  return {
    get: async (path) => unwrap(await ctx.get(`${API}${path}`, { headers })),
    post: async (path, body) => unwrap(await ctx.post(`${API}${path}`, { headers, data: body })),
    patch: async (path, body) => unwrap(await ctx.patch(`${API}${path}`, { headers, data: body })),
    put: async (path, body) => unwrap(await ctx.put(`${API}${path}`, { headers, data: body })),
  }
}

async function createTemplate(api: Api): Promise<string> {
  const tpl = await api.post('/api/v1/templates', {
    name: `E2E Campaign Template ${Date.now()}`,
    report_type: 'spot',
  })
  await api.post(`/api/v1/templates/${tpl.id}/sections`, {
    name: 'Findings',
    field_type: 'rich_text',
    grade_mode: 'numeric',
    grade_min: 0,
    grade_max: 10,
    grade_weight: 1,
  })
  await api.post(`/api/v1/templates/${tpl.id}/sections`, {
    name: 'Recommendations',
    field_type: 'rich_text',
    grade_mode: 'numeric',
    grade_min: 0,
    grade_max: 10,
    grade_weight: 1,
  })
  await api.post(`/api/v1/templates/${tpl.id}/publish`)
  return tpl.id as string
}

async function createReport(
  api: Api,
  exerciseId: string,
  templateId: string,
  teamId: string,
  name: string,
): Promise<{ id: string; sectionIds: string[] }> {
  const report = await api.post(`/api/v1/exercises/${exerciseId}/reports`, {
    template_id: templateId,
    team_id: teamId,
    name,
  })
  const sectionIds = (report.sections as { id: string }[]).map((s) => s.id)
  for (const sid of sectionIds) {
    await api.patch(`/api/v1/exercises/${exerciseId}/reports/${report.id}/sections/${sid}`, {
      version: 1,
      body: { kind: 'rich_text', content: `<p>Content for ${name}.</p>` },
    })
  }
  await api.post(`/api/v1/exercises/${exerciseId}/reports/${report.id}/submit`)
  return { id: report.id as string, sectionIds }
}

async function assignAndGrade(
  api: Api,
  exerciseId: string,
  rid: string,
  sectionIds: string[],
  adminId: string,
  grades: number[] | null,
): Promise<string> {
  const ev = await api.post(`/api/v1/exercises/${exerciseId}/reports/${rid}/evaluations`, {
    evaluator_id: adminId,
  })
  if (grades) {
    for (const [i, sid] of sectionIds.entries()) {
      await api.put(
        `/api/v1/exercises/${exerciseId}/reports/${rid}/evaluations/${ev.id}/grades/${sid}`,
        { grade: grades[i], feedback: `Feedback for section ${i + 1}.` },
      )
    }
  }
  return ev.id as string
}

async function globalSetup(): Promise<void> {
  const token = await loginAndSaveStorage()
  const ctx = await request.newContext()
  const api = makeApi(ctx, token)

  const me = await api.get('/api/v1/auth/me')
  const adminId = me.id as string

  const exercise = await api.post('/api/v1/exercises', {
    name: `E2E Campaign Exercise ${Date.now()}`,
  })
  const exerciseId = exercise.id as string
  const templateId = await createTemplate(api)

  async function team(name: string): Promise<string> {
    const t = await api.post(`/api/v1/exercises/${exerciseId}/teams`, { name, team_type: 'blue' })
    return t.id as string
  }

  const campaign = await api.post(`/api/v1/exercises/${exerciseId}/campaigns`, {
    name: 'E2E Campaign',
  })
  const campaignId = campaign.id as string

  async function addToCampaign(rid: string): Promise<void> {
    await api.post(`/api/v1/exercises/${exerciseId}/campaigns/${campaignId}/reports`, {
      report_id: rid,
    })
  }

  // Pair A: layout / stacking / finalize-bar-overlap / keyboard-order tests. Previous is
  // graded (own evaluation) but never finalized; current stays untouched by those tests.
  const teamA = await team('E2E Team A')
  const prevA = await createReport(api, exerciseId, templateId, teamA, 'Pair A — Previous')
  const currA = await createReport(api, exerciseId, templateId, teamA, 'Pair A — Current')
  await assignAndGrade(api, exerciseId, prevA.id, prevA.sectionIds, adminId, [7, 8])
  const evidA = await assignAndGrade(api, exerciseId, currA.id, currA.sectionIds, adminId, null)
  await addToCampaign(prevA.id)
  await addToCampaign(currA.id)

  // Pair B: exclusively for the grade -> save -> finalize round trip (mutates report status).
  const teamB = await team('E2E Team B')
  const prevB = await createReport(api, exerciseId, templateId, teamB, 'Pair B — Previous')
  const currB = await createReport(api, exerciseId, templateId, teamB, 'Pair B — Current')
  await assignAndGrade(api, exerciseId, prevB.id, prevB.sectionIds, adminId, [6, 6])
  const evidB = await assignAndGrade(api, exerciseId, currB.id, currB.sectionIds, adminId, null)
  await addToCampaign(prevB.id)
  await addToCampaign(currB.id)

  // Team C: a solo report — no previous entry at all (the "first report in the campaign" state).
  const teamC = await team('E2E Team C')
  const soloC = await createReport(api, exerciseId, templateId, teamC, 'Solo — First Report')
  const evidC = await assignAndGrade(api, exerciseId, soloC.id, soloC.sectionIds, adminId, null)
  await addToCampaign(soloC.id)

  // Pair D: exclusively for the mid-grading / all-graded screenshot progression.
  const teamD = await team('E2E Team D')
  const prevD = await createReport(api, exerciseId, templateId, teamD, 'Pair D — Previous')
  const currD = await createReport(api, exerciseId, templateId, teamD, 'Pair D — Current')
  await assignAndGrade(api, exerciseId, prevD.id, prevD.sectionIds, adminId, [9, 9])
  const evidD = await assignAndGrade(api, exerciseId, currD.id, currD.sectionIds, adminId, null)
  await addToCampaign(prevD.id)
  await addToCampaign(currD.id)

  writeFileSync(
    FIXTURE_FILE,
    JSON.stringify(
      {
        exerciseId,
        pairA: { rid: currA.id, evid: evidA, sectionIds: currA.sectionIds },
        pairB: { rid: currB.id, evid: evidB, sectionIds: currB.sectionIds },
        soloC: { rid: soloC.id, evid: evidC },
        pairD: { rid: currD.id, evid: evidD, sectionIds: currD.sectionIds },
      },
      null,
      2,
    ),
  )
  await ctx.dispose()
}

export default globalSetup
