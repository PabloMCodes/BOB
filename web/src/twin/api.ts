// Read-only subset of bobapp/hub/api/models/twin.py (C10).
export type Workspace = 'rover' | 'sample'
export type Delivery = 'realtime' | 'backfilled'
export type SourceMode = 'LIVE' | 'REPLAY' | 'SAMPLE'
export type Pose = { x_m: number; y_m: number; z_m: number; yaw_rad: number }
export type Session = {
  session_id: string
  track_points: number
  segments: number
  source_modes: SourceMode[]
  current: boolean
}
export type Sessions = { workspace: Workspace; sessions: Session[] }
export type Point = { seq_id: number; east_m: number; north_m: number; delivery: Delivery }
export type Track = {
  workspace: Workspace
  session_id: string
  segments: { segment: number; delivery: Delivery | 'mixed'; points: Point[] }[]
}
export type Pin = {
  kind: 'incident' | 'evidence'; id: string; label: string
  east_m: number; north_m: number; source_mode: SourceMode; delivery: Delivery
  state: string | null; end_reason: string | null; meaning: string
}
export type Pins = {
  workspace: Workspace
  session_id: string
  pins: Pin[]
  unlocalized: { kind: string; id: string; label: string; reason: string; source_mode: SourceMode; delivery: Delivery }[]
  marker: { status: 'current' | 'last_known' | 'unknown'; pose: Pose | null; age_ms: number | null; note: string }
}
export type Connection = { url: string; token: string; workspace: Workspace }
export type Snapshot = { sessions: Session[]; session: Session | null; track: Track | null; pins: Pins | null }

export function hubUrl(value: string): string {
  const url = new URL(value)
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Use an HTTP or HTTPS hub address without credentials, query parameters, or fragments.')
  }
  return url.href.replace(/\/$/, '')
}

/** The local Vite proxy keeps authenticated hub requests on the preview's origin. */
export function hubBase(value: string): string {
  const normalized = hubUrl(value)
  return import.meta.env?.DEV && normalized === hubUrl(import.meta.env.VITE_HUB_URL || 'http://127.0.0.1:8780') ? '/_bob/hub' : normalized
}

export async function readTwin(connection: Connection, selected: string, signal: AbortSignal): Promise<Snapshot> {
  async function get<T>(path: string): Promise<T> {
    const response = await fetch(`${hubBase(connection.url)}/v1/twin/${path}?workspace=${connection.workspace}`, {
      signal, cache: 'no-store', credentials: 'omit',
      headers: connection.token ? { Authorization: `Bearer ${connection.token}` } : {},
    })
    if (!response.ok) {
      if (response.status === 401) throw new Error('Hub authentication required. Enter the hub token in Connection settings.')
      if (response.status === 404) throw new Error('The twin endpoint or workspace is unavailable. Check the hub backend version and connection settings.')
      throw new Error(`Twin request failed (HTTP ${response.status}).`)
    }
    return response.json() as Promise<T>
  }
  const list = await get<Sessions>('sessions')
  if (list.workspace !== connection.workspace || !Array.isArray(list.sessions)) throw new Error('Unexpected twin sessions response.')
  // Preserve explicit selection. A disappearing session must not silently become another map.
  const session = selected ? list.sessions.find((s) => s.session_id === selected) :
    list.sessions.find((s) => s.current) ?? list.sessions.at(-1)
  if (!session) return { sessions: list.sessions, session: null, track: null, pins: null }
  const path = `sessions/${encodeURIComponent(session.session_id)}`
  const [track, pins] = await Promise.all([get<Track>(`${path}/track`), get<Pins>(`${path}/pins`)])
  if ([track, pins].some((value) => value.workspace !== connection.workspace || value.session_id !== session.session_id)
    || !Array.isArray(track.segments) || !Array.isArray(pins.pins) || !Array.isArray(pins.unlocalized) || !pins.marker) {
    throw new Error('Twin data does not match the selected workspace and session.')
  }
  return { sessions: list.sessions, session, track, pins }
}
