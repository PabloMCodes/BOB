import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { hubUrl, readTwin } from '../src/twin/api.ts'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const connection = { url: 'http://localhost:8780', token: 'test-only', workspace: 'rover' as const }
const sessions = [{ session_id: 'old', current: false }, { session_id: 'current', current: true }]

test('only twin routes are read, with one workspace and header authentication', async () => {
  const paths: string[] = []
  globalThis.fetch = async (input, options) => {
    const url = new URL(String(input))
    paths.push(url.pathname)
    assert.equal(url.search, '?workspace=rover')
    assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer test-only')
    assert.equal(options?.credentials, 'omit')
    const body = url.pathname.endsWith('/sessions') ? { workspace: 'rover', sessions } :
      url.pathname.endsWith('/track') ? { workspace: 'rover', session_id: 'current', segments: [] } :
        { workspace: 'rover', session_id: 'current', pins: [], unlocalized: [], marker: { status: 'unknown' } }
    return Response.json(body)
  }
  const result = await readTwin(connection, '', new AbortController().signal)
  assert.equal(result.session?.session_id, 'current')
  assert.deepEqual(paths, ['/v1/twin/sessions', '/v1/twin/sessions/current/track', '/v1/twin/sessions/current/pins'])
})

test('a missing selected session does not fall back to another map', async () => {
  let calls = 0
  globalThis.fetch = async () => { calls++; return Response.json({ workspace: 'rover', sessions }) }
  const result = await readTwin(connection, 'missing', new AbortController().signal)
  assert.equal(result.session, null)
  assert.equal(result.track, null)
  assert.equal(calls, 1)
})

test('sample data cannot enter the rover view', async () => {
  globalThis.fetch = async () => Response.json({ workspace: 'sample', sessions })
  await assert.rejects(readTwin(connection, '', new AbortController().signal), /Unexpected twin sessions/)
})

test('cross-session responses are rejected', async () => {
  globalThis.fetch = async (input) => Response.json(String(input).includes('/sessions?') ?
    { workspace: 'rover', sessions } : { workspace: 'rover', session_id: 'old', segments: [], pins: [], unlocalized: [], marker: {} })
  await assert.rejects(readTwin(connection, '', new AbortController().signal), /does not match/)
})

test('auth errors are actionable and cancellation is passed to every fetch', async () => {
  const controller = new AbortController()
  globalThis.fetch = async (_input, options) => {
    assert.equal(options?.signal, controller.signal)
    return new Response('', { status: 401 })
  }
  await assert.rejects(readTwin(connection, '', controller.signal), /authentication required/)
})

test('hub addresses cannot smuggle credentials or query tokens', () => {
  assert.equal(hubUrl('http://127.0.0.1:8780/'), 'http://127.0.0.1:8780')
  for (const value of ['file:///tmp/hub', 'http://user:secret@localhost', 'http://localhost?token=secret']) {
    assert.throws(() => hubUrl(value))
  }
})
