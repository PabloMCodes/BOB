import { useCallback, useEffect, useRef, useState } from 'react'
import { outcomeLabels, tally, type Tally } from './compare.ts'
import { DOWNLOAD_MB, loadEngine, PERSON_MODEL, ZERO_SHOT_MODEL, type Engine } from './engine.ts'
import { loadFixture, missingClasses, type Fixture } from './fixture.ts'
import { specs } from './prompts.ts'
import { auditAll, frameNote } from './run.ts'
import { requirements, type AuditedFrame, type Outcome, type Requirement } from './types.ts'

const verdictLabels: Record<string, string> = {
  wearing: 'Present', not_wearing: 'Missing', unverified: 'Not judged',
  unavailable: 'No rule', cannot_assess: 'Abstained',
}

const empty: Tally = tally([])

/** A second opinion on the rover's PPE decisions, computed in the viewer's own browser.
 *
 * It downloads models with different weights and architectures from the rover's SH17 detector and re-judges the same
 * published frames, then shows how the two claims relate. It is not ground truth and it is not
 * evidence: where the two differ, this panel cannot establish which claim is correct.
 */
export function AuditPanel() {
  const [fixture, setFixture] = useState<Fixture | null>(null)
  const [fixtureError, setFixtureError] = useState('')
  const [engine, setEngine] = useState<Engine | null>(null)
  const [frames, setFrames] = useState<AuditedFrame[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'running' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [fraction, setFraction] = useState<number | null>(null)
  const stop = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    loadFixture(controller.signal)
      .then(setFixture)
      .catch((cause) => { if (!controller.signal.aborted) setFixtureError(cause instanceof Error ? cause.message : 'The recorded rover verdicts are unavailable.') })
    return () => controller.abort()
  }, [])

  useEffect(() => () => { stop.current = true }, [])

  const run = useCallback(async () => {
    if (!fixture) return
    stop.current = false
    setFrames([])
    try {
      let ready = engine
      if (!ready) {
        setStatus('loading')
        ready = await loadEngine((text, value) => { setMessage(text); setFraction(value) })
        setEngine(ready)
      }
      setStatus('running')
      setMessage('')
      setFraction(null)
      await auditAll(ready, fixture, (frame) => setFrames((previous) => [...previous, frame]), () => stop.current)
      setStatus(stop.current ? 'idle' : 'done')
    } catch (cause) {
      setStatus('error')
      setMessage(cause instanceof Error ? cause.message : 'The audit could not run in this browser.')
    }
  }, [engine, fixture])

  const outcomes = frames.flatMap((frame) => requirements.map((requirement) => frame.results[requirement].outcome))
  const counts = outcomes.length > 0 ? tally(outcomes) : empty
  const busy = status === 'loading' || status === 'running'
  const perRequirement = (requirement: Requirement) => tally(frames.map((frame) => frame.results[requirement].outcome))

  return <section className="dashboard-panel dashboard-audit" aria-label="Second opinion">
    <div className="dashboard-panel-heading">
      <h2 className="eyebrow">Second opinion</h2>
      <span className="status-tag">{engine ? `${engine.info.device} · ${engine.info.dtype}` : 'Not loaded'}</span>
    </div>

    <p className="dashboard-note">
      Models with different weights and architectures from the rover's detector re-judge the same frames
      in your browser. Training-data overlap has not been verified. This panel cannot establish which claim is correct — a disagreement
      is a prompt to look, never proof the rover erred. Nothing here is evidence, and nothing is sent anywhere.
    </p>

    {fixtureError && <p className="twin-notice" role="alert">{fixtureError}</p>}

    <div className="dashboard-audit-actions">
      <button type="button" className="dashboard-audit-run" onClick={run} disabled={busy || !fixture}>
        {busy ? 'Working…' : frames.length > 0 ? 'Run again' : `Run the audit${engine ? '' : ` · ~${DOWNLOAD_MB} MB first load`}`}
      </button>
      {busy && <button type="button" className="dashboard-audit-stop" onClick={() => { stop.current = true }}>Stop</button>}
      <span className="dashboard-note">
        {status === 'idle' && frames.length === 0 && (fixture ? `${fixture.images.length} recorded frames ready. Nothing has been audited yet.` : 'Loading recorded verdicts…')}
        {status === 'loading' && `${message}${fraction == null ? '' : ` ${Math.round(fraction * 100)}%`}`}
        {status === 'running' && `Auditing frame ${frames.length + 1} of ${fixture?.images.length ?? 0}…`}
        {status === 'done' && `Audited ${frames.length} frames.`}
        {status === 'error' && message}
      </span>
    </div>

    {frames.length === 0
      ? <p className="dashboard-note mt-6">Counts appear once frames have actually been audited. An empty audit is not a clean result.</p>
      : <>
        <div className="dashboard-metrics dashboard-audit-metrics">
          {(['agree', 'disagree', 'gap', 'cannot_assess'] as Outcome[]).map((outcome) => <div className="dashboard-metric" key={outcome}>
            <span>{outcomeLabels[outcome]}</span>
            <strong>{counts[outcome]}</strong>
            <small>{outcome === 'agree' ? 'Both judged, same answer'
              : outcome === 'disagree' ? 'Both judged, different answers'
                : outcome === 'gap' ? 'Rover abstained or has no rule' : 'Auditor would not commit'}</small>
          </div>)}
        </div>

        <table className="dashboard-audit-table">
          <caption className="dashboard-note">Per requirement, over {frames.length} audited frame(s)</caption>
          <thead><tr><th scope="col">Requirement</th><th scope="col">Agree</th><th scope="col">Disagree</th><th scope="col">Rover did not judge</th><th scope="col">Auditor abstained</th><th scope="col">Note</th></tr></thead>
          <tbody>
            {requirements.map((requirement) => {
              const row = perRequirement(requirement)
              const missing = fixture ? missingClasses(fixture, requirement) : []
              return <tr key={requirement}>
                <th scope="row">{specs[requirement].label}</th>
                <td>{row.agree}</td><td>{row.disagree}</td><td>{row.gap}</td><td>{row.cannot_assess}</td>
                <td className="dashboard-note">{missing.length > 0 ? `Rover rule inactive — model has no ${missing.join(', ')} class.` : specs[requirement].note || '—'}</td>
              </tr>
            })}
          </tbody>
        </table>

        <div className="dashboard-audit-frames">
          {frames.map((frame) => <details key={frame.src}>
            <summary>
              <img src={frame.src} alt="" loading="lazy" />
              <span>{frame.src.split('/').pop()}</span>
              <span className="dashboard-audit-chips">
                {requirements.map((requirement) => <span key={requirement} className={`dashboard-audit-chip is-${frame.results[requirement].outcome}`}>
                  {specs[requirement].label}: {outcomeLabels[frame.results[requirement].outcome]}
                </span>)}
              </span>
            </summary>
            <p className="dashboard-note">
              {frameNote(frame) ?? `${frame.subjects.length} person box(es) found by the auditor · ${Math.round(frame.elapsedMs)} ms`}
            </p>
            <ul className="dashboard-audit-detail">
              {requirements.map((requirement) => <li key={requirement}>
                <strong>{specs[requirement].label}</strong>
                <span>rover: {verdictLabels[frame.results[requirement].rover]}</span>
                <span>auditor: {verdictLabels[frame.results[requirement].auditor]}</span>
                <span className="dashboard-note">{frame.subjects.map((subject, index) => {
                  const own = subject.verdicts[requirement]
                  return `#${index + 1} ${verdictLabels[own.verdict]}${own.reason ? ` (${own.reason})` : ` (margin ${own.margin.toFixed(2)})`}`
                }).join(' · ') || 'no subjects'}</span>
              </li>)}
            </ul>
          </details>)}
        </div>
      </>}

    <p className="dashboard-note mt-6">
      Auditor: {PERSON_MODEL} for people, {ZERO_SHOT_MODEL} vision tower for requirements, running on {engine?.info.device ?? 'this browser'}.
      Compared against recorded output of {fixture?.model_id ?? 'the rover pipeline'} ({fixture?.mode}@{fixture?.imgsz}), generated {fixture?.generated_utc ?? 'unknown'}.
      Supplied photographs, not rover captures — <strong>SAMPLE</strong>, never live worksite conditions.
    </p>
    <p className="dashboard-note">
      The prompts and decision margins were chosen on these same ten frames, so the counts above are calibration-set
      behaviour, not validation. No labelled ground truth exists for this set, and nothing here establishes accuracy on
      a real worksite.
    </p>
  </section>
}
