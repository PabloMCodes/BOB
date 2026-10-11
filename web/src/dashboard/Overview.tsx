import { useEffect, useState } from 'react'
import { hubBase, type Connection } from '../twin/api.ts'
import type { Status } from './api.ts'

const value = (n: number | null | undefined, unit: string) => n == null ? '—' : `${n.toFixed(1)} ${unit}`
const age = (n: number | null | undefined) => n == null ? 'Unknown' : n < 1000 ? `${Math.round(n)} ms` : `${(n / 1000).toFixed(1)} s`

export function Overview({ status, stale }: { status: Status | null; stale: boolean }) {
  const telemetry = status?.telemetry
  const current = !stale && telemetry?.current
  const live = status?.live
  const resultsFresh = current && (live?.freshness.results.age_ms ?? Infinity) + (status?.live_received_age_ms ?? Infinity) < 3000
  const metrics = [
    ['Incoming frames', current ? value(telemetry?.frame_fps, 'FPS') : '—', 'Frames admitted from the phone'],
    ['Detection throughput', current ? value(telemetry?.processing_hz, 'Hz') : '—', 'Frames processed per second'],
    ['Pose updates', current ? value(telemetry?.pose_hz, 'Hz') : '—', 'Frame and standalone pose packets'],
    ['Inference', resultsFresh ? value(telemetry?.inference_latency_ms, 'ms') : '—', 'Latest processed frame'],
    ['Detection confidence', resultsFresh && telemetry?.confidence_mean != null ? `${(telemetry.confidence_mean * 100).toFixed(1)}%` : '—', 'Mean model-box score · latest frame'],
    ['Dropped frames', !stale && status?.live_is_current ? String(live?.health?.dropped_count ?? '—') : '—', 'Phone gaps, slot drops, decode failures'],
  ]
  return <>
    <div className="dashboard-metrics">{metrics.map(([label, number, note]) => <div className="dashboard-metric" key={label}><span>{label}</span><strong>{number}</strong><small>{note}</small></div>)}</div>
    <p className="dashboard-note">{current ? `Rates measured over ${telemetry?.window_s} seconds on the rover. Confidence describes model detections, not site compliance.` : status?.telemetry_reason || 'Measured rates appear when the vision stream is active. Previous readings are not shown as current.'}</p>
    <section className="dashboard-panel" aria-label="Connections and producers">
      <div className="dashboard-panel-heading"><h2 className="eyebrow">Connections</h2><span className="dashboard-note">{status?.source_mode || 'No source publishing'}</span></div>
      <div className="dashboard-connections">
        <div><span>Hub → rover</span><strong>{stale ? 'Unknown' : status?.link.state || 'Waiting'}</strong><small>{!stale && status?.live_is_current ? 'Live state current' : 'Current rover state unknown'}</small></div>
        {['video', 'results', 'pose', 'health'].map((feed) => <div key={feed}><span>{feed === 'video' ? 'Phone frames' : feed === 'results' ? 'Vision results' : feed === 'pose' ? 'ARKit pose' : 'Stream health'}</span><strong>{stale || !status?.live_is_current ? 'Unknown' : age(live?.freshness[feed]?.age_ms)}</strong><small>{live?.freshness[feed]?.reason || 'Age reported by the rover'}</small></div>)}
      </div>
      <div className="dashboard-producers">{live?.capabilities.producers.map((producer) => <div key={producer.name}><span>{producer.name.replaceAll('_', ' ')}</span><span className="status-tag">{producer.status.replaceAll('_', ' ')}</span><p>{producer.note || 'No status note'}</p></div>) || <p className="dashboard-note">Producer capabilities will appear after the hub receives a stream.</p>}</div>
      <p className="dashboard-note">Model: {live?.capabilities.model_id || 'Unknown'} · Writer queue: {live?.edge.writer_queued ?? '—'} · Writer drops: {live?.edge.writer_dropped ?? '—'} · Writer errors: {live?.edge.writer_errors ?? '—'}</p>
      {live?.edge.last_error && <p className="twin-notice">{live.edge.last_error}</p>}
      {status?.gaps.length ? <p className="twin-notice">{status.gaps.length} recorded sync gap(s). Missing records remain missing.</p> : null}
    </section>
  </>
}

export function Preview({ connection, status, stale }: { connection: Connection; status: Status | null; stale: boolean }) {
  const [url, setUrl] = useState('')
  const [frameId, setFrameId] = useState('')
  const [note, setNote] = useState('Waiting for a preview frame.')
  useEffect(() => {
    let stopped = false
    let objectUrl = ''
    let sha = ''
    let timer: ReturnType<typeof setTimeout>
    let controller: AbortController
    async function refresh() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 6000)
      try {
        const response = await fetch(`${hubBase(connection.url)}/v1/preview/latest?workspace=${connection.workspace}`, { signal: controller.signal, credentials: 'omit', cache: 'no-store', headers: connection.token ? { Authorization: `Bearer ${connection.token}` } : {} })
        if (!response.ok) throw new Error('Waiting for the camera preview to sync.')
        const nextSha = response.headers.get('X-Sha256')
        if (!nextSha) throw new Error('Preview identity is unavailable.')
        if (nextSha !== sha) {
          const blob = await response.blob()
          if (!stopped) {
            const previous = objectUrl
            objectUrl = URL.createObjectURL(blob)
            setUrl(objectUrl); setFrameId(response.headers.get('X-Event-Id') || ''); sha = nextSha
            if (previous) URL.revokeObjectURL(previous)
          }
        }
        if (!stopped) setNote('')
      } catch (cause) {
        if (!stopped) setNote(cause instanceof Error ? cause.message : 'Preview unavailable')
      } finally {
        clearTimeout(timeout)
        if (!stopped) timer = setTimeout(refresh, document.hidden ? 3000 : 400)
      }
    }
    void refresh()
    return () => { stopped = true; controller?.abort(); clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [connection])
  return <section className="dashboard-panel dashboard-preview" aria-label="Camera preview">
    <div className="dashboard-panel-heading"><h2 className="eyebrow">Camera preview</h2><span className="status-tag">{connection.workspace === 'sample' ? 'SAMPLE' : stale || !status?.live_is_current || (status?.live?.freshness.video.age_ms ?? Infinity) + (status?.live_received_age_ms ?? Infinity) >= 3000 ? 'Last known' : 'Current stream'}</span></div>
    <div className="dashboard-preview-image">{url ? <img src={url} alt={connection.workspace === 'sample' ? 'Clearly labelled sample preview' : 'Latest annotated phone camera frame'} /> : <p>{note}</p>}</div>
    <p className="dashboard-note">{frameId ? `Frame ${frameId.slice(0, 8)}` : 'Preview frames come from the vision publisher.'} {note && url ? note : ''}</p>
  </section>
}
