import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))

interface Fixture {
  exerciseId: string
  pairA: { rid: string; evid: string; sectionIds: string[] }
  pairB: { rid: string; evid: string; sectionIds: string[] }
  soloC: { rid: string; evid: string }
  pairD: { rid: string; evid: string; sectionIds: string[] }
}

const fixture: Fixture = JSON.parse(readFileSync(`${__dirname}/.auth/fixture.json`, 'utf-8'))

function campaignUrl(rid: string, evid: string): string {
  return `/exercises/${fixture.exerciseId}/reports/${rid}/evaluations/${evid}/campaign`
}

/** Most of these checks are layout/business-logic facts that don't vary by viewport or
 *  theme — running them on every project would just repeat the same assertion 8x. Each is
 *  pinned to a single project; the dedicated screenshot test below is the one that actually
 *  needs the full viewport x colour-scheme matrix. */
const SINGLE_PROJECT = '1440-light'

test('the two panes stay aligned per section at 1440', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== SINGLE_PROJECT, 'layout check, single project is enough')
  await page.goto(campaignUrl(fixture.pairA.rid, fixture.pairA.evid))
  const rows = page.locator('[data-test^="pair-row-"]')
  await expect(rows.first()).toBeVisible()
  const count = await rows.count()
  expect(count).toBeGreaterThan(0)
  for (let i = 0; i < count; i++) {
    const row = rows.nth(i)
    const prevBox = await row.locator('[data-test^="prev-card-"]').boundingBox()
    const currBox = await row.locator('[data-test^="section-card-"]').boundingBox()
    expect(prevBox).not.toBeNull()
    expect(currBox).not.toBeNull()
    expect(Math.abs(prevBox!.y - currBox!.y)).toBeLessThanOrEqual(2)
  }
})

test('panes stack into one column at 375 with no horizontal page scroll', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== '320-light', 'single project, explicit 375 override below')
  await page.setViewportSize({ width: 375, height: 800 })
  await page.goto(campaignUrl(fixture.pairA.rid, fixture.pairA.evid))
  const row = page.locator('[data-test^="pair-row-"]').first()
  const prevBox = await row.locator('[data-test^="prev-card-"]').boundingBox()
  const currBox = await row.locator('[data-test^="section-card-"]').boundingBox()
  expect(prevBox).not.toBeNull()
  expect(currBox).not.toBeNull()
  // Stacked (single column): the current card sits below the previous one, not beside it.
  expect(currBox!.y).toBeGreaterThanOrEqual(prevBox!.y + prevBox!.height - 2)

  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth)
})

test('the finalize bar never covers the last section’s grade input', async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== SINGLE_PROJECT,
    'viewport-independent, single project is enough',
  )
  await page.goto(campaignUrl(fixture.pairA.rid, fixture.pairA.evid))
  const lastSectionId = fixture.pairA.sectionIds.at(-1)!
  const input = page.locator(`[data-test="grade-numeric-${lastSectionId}"]`)
  await input.scrollIntoViewIfNeeded()
  const inputBox = await input.boundingBox()
  const barBox = await page.locator('[data-test="finalize-bar"]').boundingBox()
  expect(inputBox).not.toBeNull()
  expect(barBox).not.toBeNull()
  expect(inputBox!.y + inputBox!.height).toBeLessThanOrEqual(barBox!.y)
})

test('grade, save, then finalize moves the report to evaluated', async ({
  page,
  request,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== SINGLE_PROJECT,
    'business-logic round trip, single project is enough',
  )
  await page.goto(campaignUrl(fixture.pairB.rid, fixture.pairB.evid))

  for (const sid of fixture.pairB.sectionIds) {
    const input = page.locator(`[data-test="grade-numeric-${sid}"]`)
    await input.fill('8')
    await input.blur()
    await expect(input).toHaveValue('8.00')
    await expect(page.locator(`[data-test="grade-error-${sid}"]`)).toHaveCount(0)
  }
  // The save round trip (PUT + re-fetch) is async — wait for the server's own confirmation
  // that every gradable section landed, not just for the local draft to show a value.
  await expect(page.locator('[data-test="finalize-remaining"]')).toHaveText('All sections graded')

  const finalizeBtn = page.locator('[data-test="finalize-btn"]')
  await expect(finalizeBtn).toBeEnabled()
  await finalizeBtn.click()
  await expect(page.locator('[data-test="finalize-error"]')).toHaveCount(0)
  await expect(page.locator('[data-test="finalize-done"]')).toBeVisible()

  const token = await page.evaluate(() => localStorage.getItem('rt_token'))
  const resp = await request.get(
    `http://localhost:8000/api/v1/exercises/${fixture.exerciseId}/reports/${fixture.pairB.rid}`,
    { headers: { Authorization: `Bearer ${token}` } },
  )
  const body = await resp.json()
  expect(body.data.status).toBe('evaluated')
})

test('keyboard tab order reaches every current-pane grade input before the finalize bar', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== SINGLE_PROJECT, 'DOM order is viewport-independent')
  await page.goto(campaignUrl(fixture.pairA.rid, fixture.pairA.evid))

  const seenInputs = new Set<string>()
  let reachedFinalizeInput = false
  // Bounded loop: fails loudly (assertion below) rather than spinning forever if focus never
  // reaches the finalize bar.
  for (let i = 0; i < 200 && !reachedFinalizeInput; i++) {
    await page.keyboard.press('Tab')
    const test_id = await page.evaluate(
      () => document.activeElement?.getAttribute('data-test') ?? null,
    )
    if (test_id?.startsWith('grade-numeric-')) seenInputs.add(test_id)
    if (test_id === 'finalize-feedback') reachedFinalizeInput = true
  }

  expect(reachedFinalizeInput).toBe(true)
  for (const sid of fixture.pairA.sectionIds) {
    expect(seenInputs.has(`grade-numeric-${sid}`)).toBe(true)
  }
})

test('captures reference screenshots for first-report, mid-grading, and all-graded states', async ({
  page,
}) => {
  await page.goto(campaignUrl(fixture.soloC.rid, fixture.soloC.evid))
  await expect(page.locator('[data-test="campaign-empty"]')).toBeVisible()
  await page.screenshot({ path: `${test.info().outputDir}/first-report.png`, fullPage: true })

  await page.goto(campaignUrl(fixture.pairD.rid, fixture.pairD.evid))
  const [firstSection] = fixture.pairD.sectionIds
  const firstInput = page.locator(`[data-test="grade-numeric-${firstSection}"]`)
  await firstInput.fill('7')
  await firstInput.blur()
  await expect(page.locator(`[data-test="grade-${firstSection}"]`)).toBeVisible()
  await page.screenshot({ path: `${test.info().outputDir}/mid-grading.png`, fullPage: true })

  const [, secondSection] = fixture.pairD.sectionIds
  const secondInput = page.locator(`[data-test="grade-numeric-${secondSection}"]`)
  await secondInput.fill('7')
  await secondInput.blur()
  await expect(page.locator('[data-test="finalize-btn"]')).toBeEnabled()
  await page.screenshot({ path: `${test.info().outputDir}/all-graded.png`, fullPage: true })
})
