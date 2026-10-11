// Optional browser acceptance with an isolated, explicitly SAMPLE hub fixture.
// BOB_PLAYWRIGHT_MODULE points to Playwright's index.mjs when installed outside this project.
import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { execFileSync, spawn } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import { setTimeout as sleep } from 'node:timers/promises'

const { chromium } = await import(process.env.BOB_PLAYWRIGHT_MODULE || 'playwright')
async function sampleFixture() {
  const record = JSON.parse(await readFile('../tests/fixtures/app/valid/record_observation_live.json', 'utf8'))
  const jpeg = execFileSync('.venv/bin/python', ['-c', "import base64; from bobapp.sample.builder import sample_jpeg; print(base64.b64encode(sample_jpeg('offline recovery browser test')[0]).decode())"], { cwd: '..' }).toString().trim()
  const sha = createHash('sha256').update(Buffer.from(jpeg, 'base64')).digest('hex')
  const frames = [0, 1].map((seq) => {
    const row = structuredClone(record)
    Object.assign(row, { source_mode: 'SAMPLE', seq: seq + 1 })
    Object.assign(row.body, { evidence_sha256: sha, scene: null })
    Object.assign(row.body.event, { event_id: randomUUID(), seq_id: seq, boxes: [], image_size: { width: 480, height: 640 }, jetson_receive_ts_ns: (Date.now() - (10 - seq) * 1000) * 1e6 })
    return { cursor: seq + 1, delivery: 'backfilled', hub_rx_wall_ns: Date.now() * 1e6, image_status: 'available', record: row }
  })
  return { jpeg, sha, frames }
}
const fixture = process.env.BOB_FRAME_FIXTURE ? JSON.parse(await readFile(process.env.BOB_FRAME_FIXTURE, 'utf8')) : await sampleFixture()
const port = 5199
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', String(port)], { stdio: 'pipe' })
let browser
try {
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}`)).ok) break } catch { /* starting */ }
    await sleep(100)
  }
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  let offline = false
  let frames = fixture.frames.slice(0, 1)
  await page.route('**/v1/**', async (route) => {
    if (offline) { await route.abort('internetdisconnected'); return }
    const url = new URL(route.request().url())
    const workspace = url.searchParams.get('workspace') || 'rover'
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'X-Sha256,X-Event-Id' }
    if (url.pathname.includes('/evidence/') || url.pathname.endsWith('/preview/latest')) {
      await route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from(fixture.jpeg, 'base64'), headers: { ...cors, 'X-Sha256': fixture.sha, 'X-Event-Id': fixture.frames[0].record.body.event.event_id } })
      return
    }
    let body = { workspace, items: [], next_after: 0 }
    if (url.pathname === '/v1/status') body = { workspace, link: { state: 'CONNECTED' }, source_mode: 'SAMPLE', live: null, live_is_current: true, lanes: {}, gaps: [], evidence: {}, frames: { total: frames.length, available: frames.length, pending_sync: 0, missing: 0, hash_mismatch: 0, backfilled: frames.length } }
    if (url.pathname === '/v1/frames') body = { workspace, items: workspace === 'sample' ? frames : [], next_after: frames.length }
    if (url.pathname === '/v1/twin/sessions') body = { workspace, sessions: [] }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body), headers: cors })
  })
  await page.goto(`http://127.0.0.1:${port}/dashboard`)
  await page.getByText('Connection settings', { exact: false }).first().click()
  await page.locator('.twin-connection select').selectOption('sample')
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await page.waitForFunction(() => document.querySelectorAll('.dashboard-frame').length === 1)
  await page.waitForFunction(() => [...document.querySelectorAll('.dashboard-frame img')].every((i) => i.complete && i.naturalWidth > 0))
  const initialImage = await page.locator('.dashboard-frame img').getAttribute('src')
  offline = true
  await context.setOffline(true)
  await page.getByText('Previously received frames remain visible.', { exact: false }).waitFor()
  assert.equal(await page.locator('.dashboard-frame img').getAttribute('src'), initialImage)
  frames = fixture.frames
  offline = false
  await context.setOffline(false)
  await page.waitForFunction(() => document.querySelectorAll('.dashboard-frame').length === 2)
  await page.waitForFunction(() => [...document.querySelectorAll('.dashboard-frame img')].every((i) => i.complete && i.naturalWidth > 0))
  await sleep(1600)
  assert.equal(await page.locator('.dashboard-frame').count(), 2)
  assert.deepEqual(errors, [])
  await mkdir('/tmp/bob-offline-browser', { recursive: true })
  await page.getByRole('region', { name: 'Saved camera frames' }).screenshot({ path: '/tmp/bob-offline-browser/recovered-frames.png' })
  console.log('Browser acceptance passed: cached frame stayed visible offline; new SAMPLE history appeared automatically after reconnect; no duplicates or page errors.')
} finally {
  await browser?.close()
  server.kill('SIGTERM')
}
