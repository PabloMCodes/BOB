import { useCallback, useState } from 'react'
import { Select } from '../components/Select.tsx'
import { hubBase, type Connection } from '../twin/api.ts'
import { errorMessage, labels, scoped, type Item, type Observation, type Page } from './api.ts'
import { usePoll } from './usePoll.ts'

const human = (value: string) => value.replaceAll('_', ' ')
const score = (value: number) => `${(value * 100).toFixed(1)}%`

function Evidence({ connection, sha }: { connection: Connection; sha: string }) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function download() {
    setBusy(true); setMessage('')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 6000)
    try {
      const response = await fetch(`${hubBase(connection.url)}/v1/evidence/${encodeURIComponent(sha)}?workspace=${connection.workspace}`, { signal: controller.signal, credentials: 'omit', headers: connection.token ? { Authorization: `Bearer ${connection.token}` } : {} })
      if (response.status === 202) { setMessage('Evidence is still syncing.'); return }
      if (response.status === 404) { setMessage('Evidence is missing.'); return }
      if (!response.ok) throw new Error(`Evidence request failed (HTTP ${response.status}).`)
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = url; link.download = `${connection.workspace}-evidence-${sha.slice(0, 12)}.jpg`; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) { setMessage(errorMessage(cause)) }
    finally { clearTimeout(timer); setBusy(false) }
  }
  return <span><button className="cursor-target dashboard-link" disabled={busy} onClick={() => void download()}>{busy ? 'Loading…' : 'Download evidence'}</button>{message && <small role="status"> {message}</small>}</span>
}

export function DetectionHistory({ connection, selected, revision }: { connection: Connection; selected: string; revision: number }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const filter = selected ? `&session_id=${encodeURIComponent(selected)}` : ''
    const [observations, incidents] = await Promise.all([
      scoped<Page<Observation>>(connection, `/v1/observations?latest=true&limit=30${filter}`, signal),
      scoped<Page>(connection, `/v1/incidents?latest=true&limit=30${filter}`, signal),
    ])
    if (selected && observations.items.some((item) => item.record.body.event.session_id !== selected)) throw new Error('Observation data does not match the selected session.')
    if (selected && incidents.items.some((item) => item.record.body.key?.session_id !== selected)) throw new Error('Incident data does not match the selected session.')
    return { observations, incidents }
  }, [connection, selected])
  const state = usePoll(load, 1500, revision)
  const observations = state.data?.observations.items || []
  const latest = observations.at(-1)?.record.body
  const assessment = latest?.assessment
  return <>
    <section className="dashboard-panel" aria-label="Latest assessment">
      <div className="dashboard-panel-heading"><h2 className="eyebrow">Latest recorded assessment</h2><span className="status-tag">{connection.workspace === 'sample' ? 'SAMPLE' : 'Frame assessment'}{state.stale ? ' · stale' : ''}</span></div>
      {assessment ? <><p className="dashboard-note">{assessment.worksite_id} · revision {assessment.profile_revision} · frame {latest?.event.seq_id} · session {latest?.event.session_id.slice(0, 8)}</p><div className="dashboard-assessments">{assessment.requirements.map((item) => <div key={item.requirement}><span>{labels[item.requirement]}</span><strong className={['not_assessed', 'assessment_unavailable'].includes(item.status) ? 'text-tape' : ''}>{human(item.status)}</strong>{item.reason && <small>{item.reason}</small>}</div>)}</div>{assessment.no_requirements_selected && <p className="twin-notice">No requirements selected. This frame does not establish compliance.</p>}</> : <p className="dashboard-note">No worksite assessment recorded for these frames. Save requirements and explicitly start an inspection to apply them.</p>}
    </section>
    <section className="dashboard-panel" aria-label="Detection history">
      <div className="dashboard-panel-heading"><h2 className="eyebrow">Detections & confidence</h2><span className="dashboard-note">Latest 30 recorded frames</span></div>
      {state.error && <p className="twin-notice" role="alert">{state.error}</p>}
      <div className="dashboard-table-wrap"><table className="dashboard-table"><thead><tr><th>Frame / source</th><th>Model</th><th>Inference</th><th>Detections</th><th>Pose / evidence</th></tr></thead><tbody>{[...observations].reverse().map((item) => {
        const body = item.record.body, event = body.event
        return <tr key={item.cursor}><td><strong>{event.seq_id}</strong><small>{item.record.source_mode} · {item.delivery}<br />Session {event.session_id.slice(0, 8)}</small></td><td>{event.model_id}</td><td>{event.inference_latency_ms.toFixed(1)} ms</td><td><details><summary className="cursor-target">{event.boxes.length} boxes</summary><ul className="dashboard-boxes">{event.boxes.map((box, i) => <li key={i}>{box.cls_name} <strong>{score(box.conf)}</strong><small>{box.source === 'derived' ? 'Derived · subject confidence' : 'Model detection'}</small></li>)}</ul></details></td><td>{event.pose_valid ? 'Valid' : human(event.pose_invalid_reason || 'Unknown')}<small>{body.evidence_sha256 && <Evidence connection={connection} sha={body.evidence_sha256} />}</small></td></tr>
      })}</tbody></table></div>
      {!observations.length && <p className="dashboard-note dashboard-empty-note">No recorded detection frames in this selection.</p>}
      <p className="dashboard-note">Each confidence belongs to its source box. Derived boxes carry subject confidence; a missing violation is not a pass.</p>
    </section>
    <section className="dashboard-panel" aria-label="Incident history"><div className="dashboard-panel-heading"><h2 className="eyebrow">Incident timeline</h2><span className="dashboard-note">Backend policy transitions · latest 30</span></div>
      <ol className="dashboard-events">{[...(state.data?.incidents.items || [])].reverse().map((item) => <li key={item.cursor}><span className="status-tag">{human(item.record.body.transition || 'Unknown')}</span><div><strong>{human(item.record.body.key?.hazard || 'Unknown')}{item.record.body.key?.rule ? ` · ${item.record.body.key.rule}` : ''}</strong><p>{item.record.source_mode} · {item.delivery} · {item.record.body.incident_id?.slice(0, 8)}{item.record.body.calibrated === false ? ' · policy uncalibrated' : ''}</p>{item.record.body.end_reason && <p>End reason: {human(item.record.body.end_reason)}</p>}{item.record.body.evidence_sha256?.map((sha) => <Evidence key={sha} connection={connection} sha={sha} />)}</div></li>)}</ol>
      {!state.data?.incidents.items.length && <p className="dashboard-note">No incident transitions recorded. This is not an all-clear.</p>}
    </section>
  </>
}

export function Logs({ connection, revision }: { connection: Connection; revision: number }) {
  const [before, setBefore] = useState<number | null>(null)
  const [kind, setKind] = useState('all')
  const load = useCallback((signal: AbortSignal) => scoped<Page>(connection, `/v1/logs?limit=50${before == null ? '' : `&before=${before}`}`, signal), [connection, before])
  const state = usePoll(load, 1500, revision)
  const items = state.data?.items || []
  const visible = items.filter((item) => kind === 'all' || item.record.body.kind === kind)
  function exportLogs() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(visible, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = `${connection.workspace}-logs.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section className="dashboard-panel" aria-label="Backend logs">
    <div className="dashboard-panel-heading"><div><h2 className="eyebrow">Backend logs</h2><p className="dashboard-note">{before == null ? 'Recent' : 'Historical'} notices, sync gaps, profile revisions and inspection events.</p></div><button className="cursor-target dashboard-button" disabled={!visible.length} onClick={exportLogs}>Export visible logs</button></div>
    <div className="dashboard-actions"><label className="twin-field dashboard-log-filter">Event type<Select data-cursor-label="Filter logs" value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">All events</option>{['notice', 'incident', 'inspection_started', 'inspection_ended', 'profile_revision', 'gap'].map((name) => <option key={name} value={name}>{human(name)}</option>)}</Select></label><button className="cursor-target dashboard-button" disabled={items.length < 50} onClick={() => setBefore(items[0]?.cursor || null)}>Older logs</button>{before != null && <button className="cursor-target dashboard-button" onClick={() => setBefore(null)}>Return to recent</button>}</div>
    {state.error && <p className="twin-notice" role="alert">{state.error}</p>}
    <div className="dashboard-log-list">{[...visible].reverse().map((item: Item) => <details key={item.cursor}><summary className="cursor-target"><time>{new Date(item.hub_rx_wall_ns / 1e6).toLocaleTimeString()}</time><span>{human(item.record.body.code || item.record.body.kind)}</span><strong>{item.record.body.message || human(item.record.body.transition || item.record.body.kind)}</strong><small>{item.record.source_mode} · {item.delivery}</small></summary><pre>{JSON.stringify(item, null, 2)}</pre></details>)}{!visible.length && <p className="dashboard-note">No logs in this page match the selected type.</p>}</div>
    <p className="dashboard-note">Times show receipt on the laptop hub. Backfilled events are history. Stream telemetry notices contain measured rates; browser credentials are never included.</p>
  </section>
}
