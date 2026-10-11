import { useEffect, useState } from 'react'
import { Select } from '../components/Select.tsx'
import { hubUrl, readTwin } from './api.ts'
import type { Connection, Snapshot, Workspace } from './api.ts'
import { TwinMap } from './TwinMap.tsx'

export function TwinView({ connection, selected, onSelect }: { connection: Connection; selected: string; onSelect: (value: string) => void }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState<Date | null>(null)
  const [stale, setStale] = useState(true)
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    let freshnessTimer: ReturnType<typeof setTimeout>
    let controller: AbortController
    async function refresh() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 6000)
      try {
        const next = await readTwin(connection, selected, controller.signal)
        if (!stopped) {
          setSnapshot(next); setUpdated(new Date()); setError(''); setStale(false)
          clearTimeout(freshnessTimer)
          freshnessTimer = setTimeout(() => setStale(true), 3000)
        }
      } catch (cause) {
        if (!stopped) {
          setStale(true)
          setError(cause instanceof Error && cause.name !== 'TypeError' && cause.name !== 'AbortError' ? cause.message :
            'Cannot reach the hub. Check that it is running, its address, and the allowed browser origin.')
        }
      } finally {
        clearTimeout(timeout)
        controller.abort()
        if (!stopped) timer = setTimeout(refresh, 1500)
      }
    }
    void refresh()
    return () => { stopped = true; clearTimeout(timer); clearTimeout(freshnessTimer); controller?.abort() }
  }, [connection, selected])

  const { sessions = [], session = null, track = null, pins = null } = snapshot ?? {}
  const markerStatus = stale ? 'unknown' : pins?.marker.status ?? 'unknown'
  return (
    <>
      <div className="twin-toolbar">
        <label className="twin-field twin-session">Session
          <Select data-cursor-label="Choose session" value={selected} onChange={(event) => onSelect(event.target.value)}>
            <option value="">Follow current / latest available</option>
            {sessions.map((item) => <option key={item.session_id} value={item.session_id}>{item.session_id.slice(0, 8)}{item.current ? ' · current' : ' · history'}</option>)}
            {selected && !sessions.some((item) => item.session_id === selected) && <option value={selected}>{selected.slice(0, 8)} · unavailable</option>}
          </Select>
        </label>
        <div className="twin-sync" role="status">
          <span className={`status-tag ${stale && updated || error ? 'text-tape' : 'text-muted'}`}>{error ? updated ? 'Twin unavailable · stale' : 'Twin unavailable' : updated ? stale ? 'Awaiting refresh · stale' : 'Twin synced' : 'Loading twin'}</span>
          <span className="text-muted text-xs">{updated ? `Last refreshed ${updated.toLocaleTimeString()}` : 'Waiting for twin data'}</span>
        </div>
      </div>
      {error && <p role="alert" className="twin-notice">{error} {snapshot ? 'The map shows the last successful response; current position is unknown.' : ''}</p>}
      {!snapshot ? <div className="twin-empty"><p className="step-title">{error ? 'The twin is waiting for a connection.' : 'Loading the twin…'}</p><p>Start the laptop hub, then connect here. No demonstration data is substituted.</p></div> : !session || !track || !pins ?
        <div className="twin-empty"><p className="step-title">{selected ? 'This session is no longer available.' : 'No sessions in this workspace yet.'}</p><p>{selected ? 'Choose another session or follow the current session.' : 'The hub needs synced camera track or observation data before a map can appear.'}</p></div> :
        <div className="twin-layout">
          <section className="twin-canvas" aria-label="Digital twin map">
            <div className="twin-map-heading"><div><p className="eyebrow text-muted">Session-local map</p><p className="mt-2 text-sm">{session.session_id.slice(0, 8)} · {session.source_modes.join(' / ') || 'Source unavailable'}</p></div><span className="status-tag">{connection.workspace === 'sample' ? 'SAMPLE' : 'ROVER DATA'}</span></div>
            <TwinMap track={track} pins={pins} stale={stale} />
            <div className="twin-legend"><span>— Camera path</span><span>┄ Backfilled history</span><span className="text-tape">○ Observation</span></div>
            <p className="twin-map-note">Metres from session origin. Up is the initial camera facing, not compass north. Tracking gaps remain separate.</p>
          </section>
          <aside className="twin-details" aria-label="Twin details">
            <p className="eyebrow text-muted">Phone camera</p>
            <h2 className="step-title mt-3">{markerStatus === 'current' ? 'Current position' : markerStatus === 'last_known' ? 'Last known position' : 'Position unknown'}</h2>
            <p className="mt-3 text-sm text-muted">{stale ? 'Data is stale. Position since the last refresh is unknown.' : pins.marker.note}</p>
            {pins.marker.pose && <p className="twin-coordinate">x {pins.marker.pose.x_m.toFixed(2)} m <span>·</span> z {pins.marker.pose.z_m.toFixed(2)} m</p>}
            <div className="twin-counts"><div><strong>{track.segments.reduce((sum, item) => sum + item.points.length, 0)}</strong><span>Track points</span></div><div><strong>{pins.pins.length}</strong><span>Placed observations</span></div></div>
            <p className="text-sm text-muted">Pins mean “observed from here”: the camera’s location, not a person’s or hazard’s position.</p>
          </aside>
          <section className="twin-observations" aria-label="Map observations">
            <h2 className="eyebrow">Map observations <span className="text-muted">/ {pins.pins.length}</span></h2>
            {pins.pins.length === 0 ? <p className="mt-4 text-sm text-muted">No positioned observations in this session.</p> :
              <ol className="twin-pin-list">{pins.pins.map((pin, i) => <li key={`${pin.kind}:${pin.id}`}><span className="twin-index">{i + 1}</span><div><p>{pin.label}</p><p className="text-xs text-muted mt-1">{pin.source_mode} · {pin.delivery}{pin.state ? ` · ${pin.state}` : ''}{pin.end_reason ? ` · ${pin.end_reason.replaceAll('_', ' ')}` : ''}</p></div></li>)}</ol>}
          </section>
          <section className="twin-unlocalized" aria-label="Unlocalized observations">
            <h2 className="eyebrow">Without a position <span className="text-muted">/ {pins.unlocalized.length}</span></h2>
            <p className="mt-3 text-sm text-muted">These observations stay off the map because their source frame had no valid position.</p>
            <ul className="twin-pin-list">{pins.unlocalized.map((item) => <li key={`${item.kind}:${item.id}`}><div><p>{item.label}</p><p className="text-xs text-muted mt-1">{item.reason.replaceAll('_', ' ')} · {item.source_mode} · {item.delivery}</p></div></li>)}</ul>
          </section>
        </div>}
    </>
  )
}

export function TwinPane() {
  const [url, setUrl] = useState(import.meta.env.VITE_HUB_URL || 'http://127.0.0.1:8780')
  const [token, setToken] = useState('')
  const [workspace, setWorkspace] = useState<Workspace>('rover')
  const [connection, setConnection] = useState<Connection>({ url, token: '', workspace: 'rover' })
  const [revision, setRevision] = useState(0)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  return (
    <section className="twin-pane" aria-label="Digital twin">
      <details className="twin-connection">
        <summary className="cursor-target" data-cursor-label="Settings">Connection settings <span className="text-muted">· {connection.workspace === 'sample' ? 'Sample workspace' : 'Rover workspace'}</span></summary>
        <form onSubmit={(event) => {
          event.preventDefault()
          try {
            const normalized = hubUrl(url)
            setConnection({ url: normalized, token: token.trim(), workspace }); setSelected(''); setRevision((value) => value + 1); setError('')
          } catch (cause) { setError(cause instanceof Error ? cause.message : 'Invalid hub address.') }
        }}>
          <label className="twin-field">Hub address<input className="cursor-target" data-cursor-label="Edit address" type="url" required value={url} onChange={(event) => setUrl(event.target.value)} /></label>
          <label className="twin-field">Hub token<input className="cursor-target" data-cursor-label="Edit token" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder="If configured on the hub" /></label>
          <label className="twin-field">Workspace<Select data-cursor-label="Choose workspace" value={workspace} onChange={(event) => setWorkspace(event.target.value as Workspace)}><option value="rover">Rover · LIVE / REPLAY</option><option value="sample">SAMPLE · demonstration</option></Select></label>
          <button type="submit" className="cursor-target twin-button" data-cursor-label="Connect">Connect</button>
          <p className="twin-form-note">Token stays in memory for this page. Sample data uses a separate workspace.</p>
          {error && <p role="alert" className="text-tape">{error}</p>}
        </form>
      </details>
      <TwinView key={`${revision}:${selected}`} connection={connection} selected={selected} onSelect={setSelected} />
    </section>
  )
}
