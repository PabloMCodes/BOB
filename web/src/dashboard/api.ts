import { hubBase, type Connection, type SourceMode, type Delivery } from '../twin/api.ts'

export const requirements = ['helmet', 'eyewear', 'vest', 'gloves', 'boots'] as const
export type Requirement = typeof requirements[number]
export const labels: Record<Requirement, string> = { helmet: 'Hard hat', eyewear: 'Safety eyewear', vest: 'High-visibility vest', gloves: 'Gloves', boots: 'Safety boots' }
export const ruleNames: Record<Requirement, string> = { helmet: 'helmet', eyewear: 'glasses', vest: 'vest', gloves: 'gloves', boots: 'boots' }
export type Requirements = Record<Requirement, boolean>
export type Profile = { worksite_id: string; revision: number; name: string; requirements: Requirements; sha256: string }
export type Worksite = { worksite_id: string; latest: Profile; active_inspection_id: string | null; active_revision: number | null; pending: boolean }
export type Rule = { name: string; active: boolean; missing_classes: string[] }
export type FeedAge = { age_ms: number | null; reason: string | null }
export type Box = { source: 'model' | 'derived'; cls_name: string; conf: number; xyxy: number[] }
export type Assessment = { inspection_id: string; worksite_id: string; profile_revision: number; no_requirements_selected: boolean; requirements: { requirement: Requirement; status: string; reason: string | null }[] }
export type Observation = { kind: 'observation'; event: { event_id: string; session_id: string; seq_id: number; iphone_frame_ts_ns: number; inference_latency_ms: number; model_id: string; boxes: Box[]; pose_valid: boolean; pose_invalid_reason: string | null }; assessment: Assessment | null; evidence_sha256: string | null }
export type RecordBody = { kind: string; message?: string; code?: string; details?: Record<string, unknown>; transition?: string; end_reason?: string; incident_id?: string; inspection_id?: string; calibrated?: boolean; key?: { hazard: string; rule: string | null; session_id: string; inspection_id: string }; evidence_sha256?: string[] }
export type Item<T = RecordBody> = { cursor: number; delivery: Delivery; hub_rx_wall_ns: number; record: { seq: number; source_mode: SourceMode; run_id: string | null; body: T } }
export type Page<T = RecordBody> = { workspace: Connection['workspace']; items: Item<T>[]; next_after: number }
export type Inspection = { inspection_id: string; worksite_id: string; profile_revision: number; source_mode: SourceMode; ended: Item | null }
export type Status = {
  workspace: Connection['workspace']; link: { state: string; last_error?: string }; live_is_current: boolean; source_mode: SourceMode | null
  live_received_age_ms: number | null; lanes: Record<string, { records: number; committed_seq: number; behind: number | null }>
  gaps: { lane: string; first_seq: number; last_seq: number; reason: string }[]; evidence: Record<string, number>
  live: { run_id: string | null; active_inspection_id: string | null; preview: { sha256: string; event_id: string; seq_id: number } | null; health: { stale: boolean; dropped_count: number; tracking_state: string | null } | null; freshness: Record<string, FeedAge>; capabilities: { model_id: string | null; rules: Rule[]; producers: { name: string; status: string; note: string | null }[] }; edge: { writer_queued: number | null; writer_dropped: number | null; writer_errors: number | null; last_error: string | null } } | null
  telemetry?: { current: boolean; session_id: string; window_s: number; age_ms: number; frame_fps: number | null; pose_hz: number | null; processing_hz: number | null; inference_latency_ms: number | null; confidence_mean: number | null } | null
  telemetry_reason?: string | null
}

export class HubError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function request<T>(connection: Connection, path: string, signal?: AbortSignal, method = 'GET', body?: unknown): Promise<T> {
  const controller = signal ? null : new AbortController()
  const timeout = controller ? setTimeout(() => controller.abort(), 6000) : null
  try {
  const response = await fetch(`${hubBase(connection.url)}${path}`, {
    signal: signal || controller?.signal, method, credentials: 'omit', cache: 'no-store',
    headers: { ...(connection.token ? { Authorization: `Bearer ${connection.token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const detail = typeof payload.detail === 'string' ? payload.detail : ''
    const message = response.status === 401 ? 'Hub authentication required. Enter your hub token in Connection settings.' :
      response.status === 409 ? `Conflict: ${detail || 'the worksite revision or active inspection changed'}. Refresh before trying again.` :
      response.status === 503 ? detail || 'Rover unavailable. The inspection command could not be completed.' :
      response.status === 404 ? 'This endpoint or workspace is unavailable. Check that the hub is running the current backend.' :
      detail || `Hub request failed (HTTP ${response.status}).`
    throw new HubError(response.status, message)
  }
  return response.json() as Promise<T>
  } finally { if (timeout) clearTimeout(timeout) }
}

export async function scoped<T extends { workspace: Connection['workspace'] }>(connection: Connection, path: string, signal: AbortSignal): Promise<T> {
  const data = await request<T>(connection, `${path}${path.includes('?') ? '&' : '?'}workspace=${connection.workspace}`, signal)
  if (data.workspace !== connection.workspace) throw new Error('The hub returned data for another workspace.')
  return data
}

export function assertRover(connection: Connection) {
  if (connection.workspace !== 'rover') throw new Error('SAMPLE is read-only. Switch to Rover to edit site requirements.')
}

export async function saveProfile(connection: Connection, id: string, profile: { expected_revision: number; name: string; requirements: Requirements }) {
  assertRover(connection)
  return request<Worksite>(connection, `/v1/worksites/${encodeURIComponent(id)}`, undefined, 'PUT', profile)
}

export function startInspection(connection: Connection, profile: Profile, mode: 'LIVE' | 'REPLAY', inspectionId: string) {
  assertRover(connection)
  return request<Item['record']>(connection, '/v1/inspections', undefined, 'POST', { worksite_id: profile.worksite_id, revision: profile.revision, source_mode: mode, inspection_id: inspectionId, requested_by: 'site manager' })
}

export function endInspection(connection: Connection, id: string) {
  assertRover(connection)
  return request<Item['record']>(connection, `/v1/inspections/${encodeURIComponent(id)}/end`, undefined, 'POST', {})
}

export function errorMessage(cause: unknown, command = false): string {
  return cause instanceof Error && cause.name !== 'TypeError' && cause.name !== 'AbortError' ? cause.message :
    command ? 'The command result is unknown. Refresh the inspection state before retrying.' :
      'Cannot reach the hub. Check its address and the allowed browser origin.'
}
