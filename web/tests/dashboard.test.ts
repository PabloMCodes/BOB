import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { endInspection, request, saveProfile, scoped, startInspection, type Profile } from '../src/dashboard/api.ts'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const connection = { url: 'http://localhost:8780', token: 'test-only', workspace: 'rover' as const }
const profile: Profile = { worksite_id: 'site-a', revision: 3, name: 'Site A', requirements: { helmet: true, eyewear: true, vest: true, gloves: false, boots: true }, sha256: '1'.repeat(64) }

test('saving requirements sends all five backend values and the expected revision', async () => {
  globalThis.fetch = async (input, options) => {
    assert.equal(String(input), 'http://localhost:8780/v1/worksites/site-a')
    assert.equal(options?.method, 'PUT')
    assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer test-only')
    assert.equal(options?.credentials, 'omit')
    assert.deepEqual(JSON.parse(String(options?.body)), { expected_revision: 2, name: 'Site A', requirements: profile.requirements })
    return Response.json({ latest: profile })
  }
  await saveProfile(connection, 'site-a', { expected_revision: 2, name: 'Site A', requirements: profile.requirements })
})

test('an inspection starts only on explicit request and binds the saved revision', async () => {
  const calls: string[] = []
  globalThis.fetch = async (input, options) => {
    calls.push(new URL(String(input)).pathname)
    if (calls.length === 1) assert.deepEqual(JSON.parse(String(options?.body)), { worksite_id: 'site-a', revision: 3, source_mode: 'LIVE', inspection_id: 'test-inspection', requested_by: 'site manager' })
    return Response.json({ body: {} })
  }
  await startInspection(connection, profile, 'LIVE', 'test-inspection')
  await endInspection(connection, 'test-inspection')
  assert.deepEqual(calls, ['/v1/inspections', '/v1/inspections/test-inspection/end'])
})

test('sample selection cannot submit any rover policy or inspection command', async () => {
  globalThis.fetch = async () => { throw new Error('A sample command must not reach the network') }
  const sample = { ...connection, workspace: 'sample' as const }
  await assert.rejects(saveProfile(sample, 'site-a', { expected_revision: 2, name: 'A', requirements: profile.requirements }), /SAMPLE is read-only/)
  assert.throws(() => startInspection(sample, profile, 'LIVE', 'test'), /SAMPLE is read-only/)
  assert.throws(() => endInspection(sample, 'test'), /SAMPLE is read-only/)
})

test('dashboard reads reject cross-workspace responses and preserve cancellation', async () => {
  const controller = new AbortController()
  globalThis.fetch = async (input, options) => {
    assert.equal(new URL(String(input)).searchParams.get('workspace'), 'rover')
    assert.equal(options?.signal, controller.signal)
    return Response.json({ workspace: 'sample' })
  }
  await assert.rejects(scoped(connection, '/v1/status', controller.signal), /another workspace/)
})

test('conflicting edits and unreachable rover commands are actionable errors', async () => {
  globalThis.fetch = async () => Response.json({ detail: 'profile revision changed' }, { status: 409 })
  await assert.rejects(request(connection, '/v1/worksites/site-a'), /Conflict.*Refresh/)
  globalThis.fetch = async () => Response.json({ detail: 'rover unreachable; nothing was started' }, { status: 503 })
  await assert.rejects(request(connection, '/v1/inspections'), /nothing was started/)
})
