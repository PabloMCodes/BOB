import { useState } from 'react'
import { hubUrl, type Connection, type Workspace } from '../twin/api.ts'

export function ConnectionSettings({ connection, onConnect }: { connection: Connection; onConnect: (value: Connection) => void }) {
  const [url, setUrl] = useState(connection.url)
  const [token, setToken] = useState(connection.token)
  const [workspace, setWorkspace] = useState<Workspace>(connection.workspace)
  const [error, setError] = useState('')
  return <details className="twin-connection">
    <summary className="cursor-target" data-cursor-label="Settings">Connection settings <span className="text-muted">· {connection.workspace === 'sample' ? 'SAMPLE workspace' : 'Rover workspace'}</span></summary>
    <form onSubmit={(event) => { event.preventDefault(); try { onConnect({ url: hubUrl(url), token: token.trim(), workspace }); setError('') } catch (cause) { setError(cause instanceof Error ? cause.message : 'Invalid hub address') } }}>
      <label className="twin-field">Hub address<input className="cursor-target" type="url" required value={url} onChange={(event) => setUrl(event.target.value)} /></label>
      <label className="twin-field">Hub token<input className="cursor-target" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Token configured on the hub" /></label>
      <label className="twin-field">Workspace<select className="cursor-target" value={workspace} onChange={(event) => setWorkspace(event.target.value as Workspace)}><option value="rover">Rover · LIVE / REPLAY</option><option value="sample">SAMPLE · demonstration</option></select></label>
      <button className="cursor-target twin-button" type="submit" data-cursor-label="Connect">Connect</button>
      <p className="twin-form-note">The token stays in memory. Data is read from the laptop hub; SAMPLE remains separate from rover data.</p>
      {error && <p className="twin-notice" role="alert">{error}</p>}
    </form>
  </details>
}
