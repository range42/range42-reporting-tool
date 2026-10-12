import { chromium, request } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const BASE = 'http://localhost:5173'
const API = 'http://localhost:8000'
const STORAGE_STATE = `${__dirname}/.auth/admin-storage.json`
const EVALUATOR_STORAGE_STATE = `${__dirname}/.auth/evaluator-storage.json`
const FIXTURE_FILE = `${__dirname}/.auth/fixture.json`
const EVALUATOR_EMAIL = 'carol@range42.local'
/** Feedback the admin leaves on pair F's previous report; the evaluator must never see it. */
export const FOREIGN_FEEDBACK_PREFIX = 'ADMIN-ONLY feedback'

/**
 * Logs the seeded `admin@range42.local` and `carol@range42.local` personas in through the real
 * Dex SSO flow (a browser, not a raw HTTP shortcut), then uses the admin's bearer token to
 * provision everything the spec needs: a template, team-pairs (two report cycles each, or one
 * solo report) and a campaign tying them together.
 *
 * Pairs A–D use the admin as the evaluator (`is_global_admin` bypasses permission and
 * team-scoping checks), which exercises the view's own logic. Pairs E and F are graded by Carol,
 * who holds only the exercise-scoped `evaluator` role: E's previous report is her own work, F's
 * was graded by the admin alone.
 */
async function loginAndSaveStorage(email: string, storagePath: string): Promise<string> {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  await page.goto(`${BASE}/login`)
  await page.getByRole('button', { name: /sign in with sso/i }).click()
  await page.fill('#login', email)
  await page.fill('#password', 'changeme')
  await page.click('#submit-login')
  await page.waitForFunction(() => localStorage.getItem('rt_token'), null, { timeout: 15000 })
  const token = await page.evaluate(() => localStorage.getItem('rt_token'))
  if (!token) throw new Error(`${email} login did not produce a token`)
  await page.context().storageState({ path: storagePath })
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

/** Assigns `evaluatorId` (via the admin `api`) and, when `grades` is given, writes them with
 *  `grader` — grades can only be written by the assigned evaluator themselves. */
async function assignAndGrade(
  api: Api,
  exerciseId: string,
  rid: string,
  sectionIds: string[],
  evaluatorId: string,
  grades: number[] | null,
  { grader = api, feedbackPrefix = 'Feedback for section' } = {},
): Promise<string> {
  const ev = await api.post(`/api/v1/exercises/${exerciseId}/reports/${rid}/evaluations`, {
    evaluator_id: evaluatorId,
  })
  if (grades) {
    for (const [i, sid] of sectionIds.entries()) {
      await grader.put(
        `/api/v1/exercises/${exerciseId}/reports/${rid}/evaluations/${ev.id}/grades/${sid}`,
        { grade: grades[i], feedback: `${feedbackPrefix} ${i + 1}.` },
      )
    }
  }
  return ev.id as string
}

async function globalSetup(): Promise<void> {
  const token = await loginAndSaveStorage('admin@range42.local', STORAGE_STATE)
  const evaluatorToken = await loginAndSaveStorage(EVALUATOR_EMAIL, EVALUATOR_STORAGE_STATE)
  const ctx = await request.newContext()
  const api = makeApi(ctx, token)
  const evaluatorApi = makeApi(ctx, evaluatorToken)

  const me = await api.get('/api/v1/auth/me')
  const adminId = me.id as string
  const evaluatorId = (await evaluatorApi.get('/api/v1/auth/me')).id as string

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

  await api.post(`/api/v1/exercises/${exerciseId}/roles`, {
    user_id: evaluatorId,
    role_key: 'evaluator',
  })
  const asEvaluator = { grader: evaluatorApi, feedbackPrefix: 'Carol feedback' }

  // Pair E: Carol graded the previous report herself — her own grade and feedback show.
  const teamE = await team('E2E Team E')
  const prevE = await createReport(api, exerciseId, templateId, teamE, 'Pair E — Previous')
  const currE = await createReport(api, exerciseId, templateId, teamE, 'Pair E — Current')
  await assignAndGrade(
    api,
    exerciseId,
    prevE.id,
    prevE.sectionIds,
    evaluatorId,
    [6, 7],
    asEvaluator,
  )
  const evidE = await assignAndGrade(api, exerciseId, currE.id, currE.sectionIds, evaluatorId, null)
  await addToCampaign(prevE.id)
  await addToCampaign(currE.id)

  // Pair F: only the admin graded (and finalized) the previous report — Carol must see the
  // report's aggregate grade, never the admin's per-section grades or feedback.
  const teamF = await team('E2E Team F')
  const prevF = await createReport(api, exerciseId, templateId, teamF, 'Pair F — Previous')
  const currF = await createReport(api, exerciseId, templateId, teamF, 'Pair F — Current')
  const prevEvidF = await assignAndGrade(
    api,
    exerciseId,
    prevF.id,
    prevF.sectionIds,
    adminId,
    [9, 8],
    {
      feedbackPrefix: FOREIGN_FEEDBACK_PREFIX,
    },
  )
  await api.post(
    `/api/v1/exercises/${exerciseId}/reports/${prevF.id}/evaluations/${prevEvidF}/finalize`,
  )
  const evidF = await assignAndGrade(api, exerciseId, currF.id, currF.sectionIds, evaluatorId, null)
  await addToCampaign(prevF.id)
  await addToCampaign(currF.id)

  writeFileSync(
    FIXTURE_FILE,
    JSON.stringify(
      {
        exerciseId,
        pairA: { rid: currA.id, evid: evidA, sectionIds: currA.sectionIds },
        pairB: { rid: currB.id, evid: evidB, sectionIds: currB.sectionIds },
        soloC: { rid: soloC.id, evid: evidC },
        pairD: { rid: currD.id, evid: evidD, sectionIds: currD.sectionIds },
        pairE: { rid: currE.id, evid: evidE, sectionIds: currE.sectionIds },
        pairF: { rid: currF.id, evid: evidF, sectionIds: currF.sectionIds },
      },
      null,
      2,
    ),
  )
  await ctx.dispose()
}

export default globalSetup
