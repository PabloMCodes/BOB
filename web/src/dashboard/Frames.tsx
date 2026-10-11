import { useCallback, useEffect, useState } from 'react'
import { hubBase, type Connection } from '../twin/api.ts'
import { scoped, type Box, type Item, type Observation, type Status } from './api.ts'
import { usePoll } from './usePoll.ts'
import './frames.css'

type Frame = Item<Observation & { event: Observation['event'] & {
  jetson_receive_ts_ns: number; image_size: { width: number; height: number }
} }> & { image_status: 'available' | 'pending_sync' | 'missing' | 'hash_mismatch' }
type FramePage = { workspace: Connection['workspace']; items: Frame[]; next_after: number }

function FrameImage({ connection, frame }: { connection: Connection; frame: Frame }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const sha = frame.record.body.evidence_sha256
  useEffect(() => {
    if (frame.image_status !== 'available' || !sha) return
    let stopped = false, objectUrl = ''
    let timer: ReturnType<typeof setTimeout>
    let controller: AbortController
    async function load() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 6000)
      try {
        const response = await fetch(`${hubBase(connection.url)}/v1/evidence/${sha}?workspace=${connection.workspace}`, {
          signal: controller.signal, credentials: 'omit', cache: 'no-store',
          headers: connection.token ? { Authorization: `Bearer ${connection.token}` } : {},
        })
        if (response.status !== 200) throw new Error('Image is not available yet.')
        const blob = await response.blob()
        if (!stopped) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); setError('') }
      } catch {
        if (!stopped) { setError('Image transfer pending. Retrying…'); timer = setTimeout(load, 1500) }
      } finally { clearTimeout(timeout) }
    }
    void load()
    return () => { stopped = true; clearTimeout(timer); controller?.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [connection, sha, frame.image_status])
  const event = frame.record.body.event
  const { width, height } = event.image_size
  return <div className="dashboard-saved-image" style={{ aspectRatio: `${width} / ${height}` }}>
    {url ? <><img src={url} alt={`Saved model frame ${event.seq_id}`} />
      <svg viewBox={`0 0 ${width} ${height}`} aria-label="Detections from this saved frame">{event.boxes.map((box: Box, i) => {
        const [x, y, x2, y2] = box.xyxy
        const color = box.source === 'derived' ? '#ff776b' : '#f6d34e'
        return <g key={i}><rect x={x} y={y} width={x2 - x} height={y2 - y} fill="none" stroke={color} strokeWidth={Math.max(2, width / 400)} /><text x={x} y={Math.max(height / 35, y - 5)} fill={color} stroke="#111" strokeWidth={width / 1000} paintOrder="stroke" fontSize={width / 35}>{box.cls_name} {Math.round(box.conf * 100)}%</text></g>
      })}</svg></> : <p>{error || (frame.image_status === 'pending_sync' ? 'Downloading from BOB…' : frame.image_status === 'available' ? 'Loading saved frame…' : 'Image unavailable')}</p>}
  </div>
}

export function Frames({ connection, status, stale, selected }: {
  connection: Connection; status: Status | null; stale: boolean; selected: string
}) {
  const [recovered, setRecovered] = useState(true)
  const [before, setBefore] = useState<number | null>(null)
  const load = useCallback((signal: AbortSignal) => scoped<FramePage>(connection,
    `/v1/frames?limit=12${recovered ? '&delivery=backfilled' : ''}${before ? `&before=${before}` : ''}${selected ? `&session_id=${encodeURIComponent(selected)}` : ''}`, signal), [connection, recovered, before, selected])
  const state = usePoll(load, 1000)
  const frames = state.data?.items || []
  const counts = status?.frames
  const lost = stale || !status?.live_is_current
  const pending = counts?.pending_sync || 0
  return <section className="dashboard-panel" aria-label="Saved camera frames">
    <div className="dashboard-panel-heading"><div><h2 className="eyebrow">Saved camera frames</h2><p className="dashboard-note">BOB saves processed frames locally. Images appear here automatically as they reach the laptop.</p></div><span className="status-tag">{lost ? 'Connection lost · last known' : pending ? `Recovering ${pending} images` : status?.link.state === 'CATCHING_UP' ? 'Recovering saved records' : 'Connected'}</span></div>
    <p className="dashboard-note">{counts ? `${counts.available} / ${counts.total} saved frames on this laptop · ${counts.backfilled} history frames received through catch-up` : 'Waiting for saved-frame counts.'}{stale ? ' · Last known counts' : ''}</p>
    {lost && <p className="twin-notice">Previously received frames remain visible. Saved frames will resume transferring when the connection returns.</p>}
    {!!counts && counts.missing + counts.hash_mismatch > 0 && <p className="twin-notice">{counts.missing + counts.hash_mismatch} frame image(s) unavailable. These are not counted as downloaded.</p>}
    <div className="dashboard-actions"><button className="cursor-target dashboard-button" aria-pressed={recovered} onClick={() => { setRecovered(true); setBefore(null) }}>Recovered history</button><button className="cursor-target dashboard-button" aria-pressed={!recovered} onClick={() => { setRecovered(false); setBefore(null) }}>All saved frames</button>{before != null && <button className="cursor-target dashboard-button" onClick={() => setBefore(null)}>Return to newest</button>}</div>
    {state.error && <p className="twin-notice" role="alert">{state.error}</p>}
    <div className="dashboard-frames">{[...frames].reverse().map((frame) => <article key={`${frame.cursor}-${frame.record.body.event.event_id}`} className="dashboard-frame">
      <FrameImage connection={connection} frame={frame} />
      <div><span className="status-tag">{frame.record.source_mode} · {frame.delivery === 'backfilled' ? 'Recovered history' : 'Streamed'}</span><strong>Frame {frame.record.body.event.seq_id}</strong>
        <p>Captured on BOB: {new Date(frame.record.body.event.jetson_receive_ts_ns / 1e6).toLocaleTimeString()}</p><p>Received on laptop: {new Date(frame.hub_rx_wall_ns / 1e6).toLocaleTimeString()}</p><small>{frame.record.body.event.model_id} · {frame.record.body.event.boxes.length} boxes · session {frame.record.body.event.session_id.slice(0, 8)}</small></div>
    </article>)}</div>
    {!frames.length && <p className="dashboard-note">{recovered ? 'No recovered frames in this selection yet. They appear as saved history arrives after connection.' : 'No saved model frames in this selection yet.'}</p>}
    <button className="cursor-target dashboard-button" disabled={frames.length < 12} onClick={() => setBefore(frames[0]?.cursor || null)}>Older frames</button>
    <p className="dashboard-note">These are recorded observations, not current conditions. Capture and receipt times use their respective devices’ clocks. Boxes belong to each image’s original model result.</p>
  </section>
}
