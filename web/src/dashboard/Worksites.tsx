import { useCallback, useEffect, useId, useState } from 'react'
import { Select } from '../components/Select.tsx'
import type { Connection } from '../twin/api.ts'
import { endInspection, errorMessage, labels, request, requirements, ruleNames, saveProfile, scoped, startInspection, type Inspection, type Profile, type Requirements, type Status, type Worksite } from './api.ts'
import { usePoll } from './usePoll.ts'

const none = Object.fromEntries(requirements.map((name) => [name, false])) as Requirements

function Editor({ connection, site, status, active, onRefresh }: { connection: Connection; site: Worksite | null; status: Status | null; active: Inspection | null; onRefresh: () => void }) {
  const editorId = useId()
  const [id, setId] = useState(site?.worksite_id || '')
  const [name, setName] = useState(site?.latest.name || '')
  const [checks, setChecks] = useState<Requirements>(site?.latest.requirements || none)
  const [saved, setSaved] = useState<Profile | null>(site?.latest || null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [pendingCommand, setPendingCommand] = useState(false)
  useEffect(() => { if (active) setPendingCommand(false) }, [active?.inspection_id])
  const dirty = !saved || saved.name !== name || requirements.some((r) => saved.requirements[r] !== checks[r])
  const mode = status?.live_is_current && (status.source_mode === 'LIVE' || status.source_mode === 'REPLAY') ? status.source_mode : null
  async function action(task: () => Promise<unknown>, success: string) {
    setBusy(true); setError(''); setMessage('')
    try { await task(); setMessage(success); onRefresh() }
    catch (cause) { setError(errorMessage(cause, true)) }
    finally { setBusy(false) }
  }
  return <form onSubmit={(event) => { event.preventDefault(); void action(async () => {
    const result = await saveProfile(connection, id, { expected_revision: saved?.revision || 0, name, requirements: checks })
    setSaved(result.latest)
  }, 'Requirements saved. They apply to the next explicitly started inspection.') }}>
    <div className="dashboard-editor-fields">
      <label className="twin-field">Worksite ID<input className="cursor-target" value={id} disabled={!!saved || busy} required maxLength={64} pattern="[A-Za-z0-9_.\-]+" placeholder="site-a" onChange={(event) => setId(event.target.value)} /></label>
      <label className="twin-field">Worksite name<input className="cursor-target" value={name} disabled={busy} required maxLength={200} placeholder="Construction site" onChange={(event) => setName(event.target.value)} /></label>
    </div>
    <fieldset className="dashboard-requirements" disabled={busy}><legend className="dashboard-note">Required PPE for this worksite</legend>
      {requirements.map((requirement) => {
        const capability = status?.live?.capabilities.rules.find((rule) => rule.name === ruleNames[requirement])
        const hintId = `${editorId}-${requirement}-hint`
        return <label className="dashboard-requirement" key={requirement}>
          <span className="dashboard-requirement-copy"><strong>{labels[requirement]}</strong><small id={hintId}>{capability?.active ? 'Rule available' : capability ? `Assessment unavailable · missing ${capability.missing_classes.join(', ')}` : 'Rule availability unknown until a stream connects'}</small></span>
          <Select
            name={requirement}
            aria-label={labels[requirement]}
            aria-describedby={hintId}
            data-cursor-label="Choose requirement"
            value={checks[requirement] ? 'required' : 'not_required'}
            onChange={(event) => {
              const required = event.currentTarget.value === 'required'
              setChecks((current) => ({ ...current, [requirement]: required }))
            }}
          >
            <option value="required">Required</option>
            <option value="not_required">Not required</option>
          </Select>
        </label>
      })}
    </fieldset>
    <p className="dashboard-note">“Not required” excludes that PPE check from this worksite’s inspection. {requirements.every((r) => !checks[r]) ? 'No PPE requirements selected; this is not an all-clear.' : 'An uncertain or unsupported check stays unverified.'}</p>
    <div className="dashboard-actions">
      <button className="cursor-target twin-button" disabled={busy || !dirty} type="submit">{busy ? 'Working…' : 'Save requirements'}</button>
      <button className="cursor-target dashboard-button" type="button" disabled={busy || dirty || !saved || !mode || !!active || pendingCommand} onClick={() => { if (saved && mode) void action(async () => { await startInspection(connection, saved, mode, crypto.randomUUID()); setPendingCommand(true) }, `Inspection start accepted for revision ${saved.revision}. Waiting for rover sync.`) }}>Start inspection</button>
      {site && <button className="cursor-target dashboard-button" type="button" disabled={busy} onClick={() => void action(async () => { const latest = await request<Worksite>(connection, `/v1/worksites/${encodeURIComponent(site.worksite_id)}`); setSaved(latest.latest); setName(latest.latest.name); setChecks(latest.latest.requirements); setPendingCommand(false) }, 'Loaded the latest saved revision.')}>Reload saved requirements</button>}
    </div>
    <p className="dashboard-note">{saved ? `Editing saved revision ${saved.revision}. ` : 'Save a worksite before starting. '}{active ? `Active inspection: ${active.worksite_id}, revision ${active.profile_revision}. ` : ''}{!mode ? 'A connected LIVE or REPLAY publisher is required to start.' : `Source: ${mode}.`}</p>
    {site?.pending && <p className="twin-notice">Saved revision {site.latest.revision} is pending. The active inspection continues using revision {site.active_revision}.</p>}
    {message && <p className="dashboard-feedback" role="status">{message}</p>}{error && <p className="twin-notice" role="alert">{error}</p>}
  </form>
}

export function Worksites({ connection, status, revision, onRefresh }: { connection: Connection; status: Status | null; revision: number; onRefresh: () => void }) {
  const [selected, setSelected] = useState('')
  const [newSite, setNewSite] = useState(false)
  const [ending, setEnding] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const load = useCallback((signal: AbortSignal) => Promise.all([
    request<{ items: Worksite[] }>(connection, '/v1/worksites', signal),
    scoped<{ workspace: Connection['workspace']; items: Inspection[] }>(connection, '/v1/inspections', signal),
  ]), [connection])
  const state = usePoll(load, 1500, revision)
  const sites = state.data?.[0].items || []
  const site = newSite ? null : sites.find((item) => item.worksite_id === selected) || sites[0] || null
  const inspection = state.data?.[1].items.find((item) => !item.ended) || null
  const active = inspection || (status?.live?.active_inspection_id ? { inspection_id: status.live.active_inspection_id, worksite_id: 'Awaiting sync', profile_revision: 0, source_mode: status.source_mode || 'LIVE', ended: null } as Inspection : null)
  return <section className="dashboard-panel" aria-label="Site requirements">
    <div className="dashboard-panel-heading"><div><h2 className="eyebrow">Site requirements</h2><p className="dashboard-note">Validated by the site manager, assessed by the backend.</p></div>{active && <span className="status-tag">Inspection active{state.stale ? ' · last known' : ''}</span>}</div>
    {state.error && <p className="twin-notice" role="alert">{state.error}</p>}
    <div className="dashboard-site-picker"><label className="twin-field">Worksite<Select data-cursor-label="Choose worksite" value={newSite || !site ? 'create' : `site:${site.worksite_id}`} onChange={(event) => { const value = event.currentTarget.value; setNewSite(value === 'create'); setSelected(value === 'create' ? '' : value.slice(5)) }}><option value="create">Create a worksite</option>{sites.length > 0 && <optgroup label="Saved worksites">{sites.map((item) => <option key={item.worksite_id} value={`site:${item.worksite_id}`}>{item.latest.name} · {item.worksite_id} · r{item.latest.revision}</option>)}</optgroup>}</Select></label>
      {active && <button className="cursor-target dashboard-button" disabled={ending || state.stale} onClick={() => {
        setEnding(true); setError(''); setMessage('')
        void endInspection(connection, active.inspection_id).then(() => { setMessage('Inspection end accepted. Waiting for rover sync.'); onRefresh() }).catch((cause) => setError(errorMessage(cause, true))).finally(() => setEnding(false))
      }}>{ending ? 'Ending…' : 'End current inspection'}</button>}
    </div>
    <Editor key={site ? `site:${site.worksite_id}` : 'create'} site={site} connection={connection} status={status} active={active} onRefresh={onRefresh} />
    {message && <p className="dashboard-feedback" role="status">{message}</p>}{error && <p className="twin-notice" role="alert">{error}</p>}
  </section>
}
