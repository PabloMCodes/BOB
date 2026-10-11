import { lazy, Suspense, useCallback, useState } from 'react'
import type { Connection } from '../twin/api.ts'
import { TwinView } from '../twin/TwinPane.tsx'
import { scoped, type Status } from './api.ts'
import { ConnectionSettings } from './ConnectionSettings.tsx'
import { DetectionHistory, Logs } from './History.tsx'
import { Overview, Preview } from './Overview.tsx'
import { Worksites } from './Worksites.tsx'
import { usePoll } from './usePoll.ts'
import { Frames } from './Frames.tsx'

/** The auditor pulls in transformers.js, so it is split out of the dashboard bundle and only
 *  fetched when the panel renders. The models themselves load on an explicit click. */
const AuditPanel = lazy(() => import('../audit/index.ts').then((module) => ({ default: module.AuditPanel })))

function WorkspaceDashboard({ connection }: { connection: Connection }) {
  const [selected, setSelected] = useState('')
  const [revision, setRevision] = useState(0)
  const load = useCallback((signal: AbortSignal) => scoped<Status>(connection, '/v1/status', signal), [connection])
  const status = usePoll(load, 500, revision)
  const refresh = () => setRevision((value) => value + 1)
  return <>
    <div className="dashboard-health" role="status"><span className="status-tag">{status.error ? status.error.includes('authentication') ? 'Authentication required' : status.data ? 'Hub disconnected · stale' : 'Hub disconnected' : status.updated ? status.stale ? 'Awaiting refresh · stale' : 'Hub connected' : 'Connecting'}</span><span>{connection.workspace === 'sample' ? 'SAMPLE · demonstration' : 'Rover workspace'} · {status.updated ? `Last refreshed ${status.updated.toLocaleTimeString()}` : 'Waiting for backend data'}</span></div>
    {status.error && <p className="twin-notice" role="alert">{status.error}</p>}
    <Overview status={status.data} stale={status.stale} />
    <div className="dashboard-main-grid"><Preview connection={connection} status={status.data} stale={status.stale} />{connection.workspace === 'rover' ? <Worksites connection={connection} status={status.stale ? null : status.data} revision={revision} onRefresh={refresh} /> : <section className="dashboard-panel"><h2 className="eyebrow">SAMPLE inspection</h2><p className="dashboard-note mt-6">Demonstration data is read-only. Switch to Rover to validate your worksite’s requirements and explicitly start an inspection.</p><p className="dashboard-note mt-4">The recorded sample below includes detected, not required, not assessed, and unavailable checks.</p></section>}</div>
    <section className="dashboard-panel dashboard-twin" aria-label="Digital twin"><div className="dashboard-panel-heading"><h2 className="eyebrow">Digital twin</h2><span className="dashboard-note">Phone-camera observation trail</span></div><TwinView key={selected} connection={connection} selected={selected} onSelect={setSelected} /></section>
    <Suspense fallback={<section className="dashboard-panel"><h2 className="eyebrow">Second opinion</h2><p className="dashboard-note mt-6">Loading the auditor…</p></section>}><AuditPanel /></Suspense>
    <DetectionHistory key={selected} connection={connection} selected={selected} revision={revision} />
    <Frames key={`frames-${selected}`} connection={connection} selected={selected} status={status.data} stale={status.stale} />
    <Logs connection={connection} revision={revision} />
  </>
}

export function Dashboard() {
  const [connection, setConnection] = useState<Connection>({ url: import.meta.env.VITE_HUB_URL || 'http://127.0.0.1:8780', token: '', workspace: 'rover' })
  const [generation, setGeneration] = useState(0)
  return <div className="dashboard"><ConnectionSettings connection={connection} onConnect={(value) => { setConnection(value); setGeneration((n) => n + 1) }} /><WorkspaceDashboard key={generation} connection={connection} /></div>
}
