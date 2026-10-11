import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Item, Observation } from '../src/dashboard/api.ts'
import { detectionCsv } from '../src/dashboard/detectionCsv.ts'

const snapshot = { workspace: 'rover' as const, stale: false, refreshedAt: new Date('2026-10-11T16:00:00Z'), exportedAt: new Date('2026-10-11T16:01:00Z') }
const observation: Item<Observation> = {
  cursor: 12, delivery: 'realtime', hub_rx_wall_ns: 1_791_734_400_000_000_000,
  record: { seq: 4, source_mode: 'LIVE', run_id: 'run-a', body: {
    kind: 'observation', evidence_sha256: 'private-image-reference',
    event: { event_id: 'event-a', session_id: 'session-a', seq_id: 8, iphone_frame_ts_ns: 100,
      inference_latency_ms: 42.75, model_id: 'model-a', pose_valid: false, pose_invalid_reason: 'no_pose',
      boxes: [
        { cls_name: 'helmet', conf: 0.923, source: 'model', xyxy: [0, 0, 10, 10] },
        { cls_name: 'no-safety-vest', conf: 0.85, source: 'derived', xyxy: [0, 0, 20, 20] },
      ] },
    assessment: { inspection_id: 'inspection-a', worksite_id: 'site-a', profile_revision: 2, no_requirements_selected: false,
      requirements: [
        { requirement: 'helmet', status: 'detected', reason: null },
        { requirement: 'eyewear', status: 'not_assessed', reason: 'clear eyewear is uncertain' },
        { requirement: 'vest', status: 'not_detected', reason: null },
        { requirement: 'gloves', status: 'not_required', reason: null },
        { requirement: 'boots', status: 'assessment_unavailable', reason: 'model lacks safety-boots' },
      ] },
  } },
}

// Read quoted CSV including embedded quotes and multiline fields for round-trip assertions.
function records(csv: string): Record<string, string>[] {
  const rows: string[][] = []
  let row: string[] = [], value = '', quoted = false
  const input = csv.replace(/^\uFEFF/u, '')
  for (let i = 0; i < input.length; i++) {
    const char = input[i]
    if (char === '"') {
      if (quoted && input[i + 1] === '"') { value += '"'; i++ }
      else quoted = !quoted
    } else if (!quoted && (char === ',' || char === '\r')) {
      row.push(value); value = ''
      if (char === '\r') { assert.equal(input[++i], '\n'); rows.push(row); row = [] }
    } else value += char
  }
  assert.equal(quoted, false)
  assert.equal(value, '')
  const [header, ...data] = rows
  return data.map((values) => {
    assert.equal(values.length, header.length)
    return Object.fromEntries(header.map((key, index) => [key, values[index]]))
  })
}

test('export preserves confidence basis and all frame assessment states without leaking evidence', () => {
  const csv = detectionCsv([observation], snapshot)
  const [model, derived] = records(csv)
  assert.equal(model.worksite_id, 'site-a')
  assert.equal(model.session_id, 'session-a')
  assert.equal(model.profile_revision, '2')
  assert.equal(model.inference_ms, '42.75')
  assert.equal(model.source_mode, 'LIVE')
  assert.equal(model.assessment_recorded, 'true')
  assert.equal(model.frame_helmet_status, 'detected')
  assert.equal(model.frame_eyewear_status, 'not_assessed')
  assert.equal(model.frame_eyewear_reason, 'clear eyewear is uncertain')
  assert.equal(model.frame_vest_status, 'not_detected')
  assert.equal(model.frame_gloves_status, 'not_required')
  assert.equal(model.frame_boots_status, 'assessment_unavailable')
  assert.equal(model.frame_boots_reason, 'model lacks safety-boots')
  assert.equal(model.confidence_pct, '92.3')
  assert.equal(model.confidence_basis, 'detection')
  assert.equal(derived.confidence_pct, '85.0')
  assert.equal(derived.confidence_basis, 'subject')
  assert.equal(derived.frame_eyewear_status, 'not_assessed')
  assert.equal(csv.includes('private-image-reference'), false)
  assert.equal(csv.includes('xyxy'), false)
  assert.equal(csv.includes('compliant'), false)
})

test('empty frames and missing assessments stay distinct from pass; replay/sample provenance and stale snapshots persist', () => {
  const empty: Item<Observation> = { ...observation, cursor: 13, delivery: 'backfilled', record: { ...observation.record,
    source_mode: 'REPLAY', body: { ...observation.record.body, assessment: null,
      event: { ...observation.record.body.event, seq_id: 9, boxes: [] } } } }
  const sample: Item<Observation> = { ...observation, record: { ...observation.record, source_mode: 'SAMPLE',
    body: { ...observation.record.body, assessment: { ...observation.record.body.assessment!, no_requirements_selected: true,
      requirements: observation.record.body.assessment!.requirements.map((item) => ({ ...item, status: 'not_required', reason: null })) },
      event: { ...observation.record.body.event, boxes: [{ cls_name: 'person', conf: 0, source: 'model', xyxy: [0, 0, 1, 1] }] } } } }
  const original = structuredClone(empty)
  const [missing, noRequirements] = records(detectionCsv([sample, empty], { ...snapshot, workspace: 'sample', stale: true, refreshedAt: null }))
  assert.equal(missing.frame_seq, '9')
  assert.equal(missing.source_mode, 'REPLAY')
  assert.equal(missing.delivery, 'backfilled')
  assert.equal(missing.snapshot_stale, 'true')
  assert.equal(missing.last_refreshed_at_utc, '')
  assert.equal(missing.exported_at_utc, '2026-10-11T16:01:00.000Z')
  assert.equal(missing.assessment_recorded, 'false')
  assert.equal(missing.worksite_id, '')
  assert.equal(missing.frame_detection_count, '0')
  assert.equal(missing.detection_class, '')
  assert.equal(missing.confidence_pct, '')
  assert.equal(missing.frame_helmet_status, '')
  assert.equal(noRequirements.source_mode, 'SAMPLE')
  assert.equal(noRequirements.workspace, 'sample')
  assert.equal(noRequirements.no_requirements_selected, 'true')
  assert.equal(noRequirements.frame_helmet_status, 'not_required')
  assert.equal(noRequirements.confidence_pct, '0.0')
  assert.deepEqual(empty, original)
})

test('CSV round-trips Unicode, delimiters and newlines while neutralizing spreadsheet formulas', () => {
  const assessment = observation.record.body.assessment!
  for (const text of ['=1+1', '  +1+1', '-1+1', '@SUM(1,1)', '\t=1+1', '\r=1+1']) {
    const value: Item<Observation> = { ...observation, record: { ...observation.record, body: { ...observation.record.body,
      assessment: { ...assessment, worksite_id: text, requirements: [{ requirement: 'eyewear', status: 'not_assessed', reason: 'Unverified, "occluded"\r\nÉquipe' }] } } } }
    const [row] = records(detectionCsv([value], snapshot))
    assert.equal(row.worksite_id, `'${text}`)
    assert.equal(row.frame_eyewear_reason, 'Unverified, "occluded"\r\nÉquipe')
  }
  assert.equal(records(detectionCsv([], snapshot)).length, 0)
})
