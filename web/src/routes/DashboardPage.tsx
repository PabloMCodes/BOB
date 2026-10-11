import { Link } from 'react-router-dom'
import { copy } from '../data/copy.ts'
import { workerPolicy } from '../data/privacy.ts'
import { Dashboard } from '../dashboard/Dashboard.tsx'

export function DashboardPage() {
  return (
    <main className="page-inset min-h-svh pb-16 pt-28">
      <div className="twin-title">
        <p className="eyebrow text-muted">{copy.dashboard.eyebrow}</p>
        <h1 className="chapter-title mt-6 text-ink">{copy.dashboard.title}</h1>
        <p className="body-copy mt-6 text-muted">{copy.dashboard.sentence}</p>
        <p className="mt-6 max-w-2xl text-xs leading-relaxed text-muted">
          Image policy: {workerPolicy.retention[0].period} for routine images, {workerPolicy.retention[1].period} for incident evidence. Deletion is operator-managed.{' '}
          <Link to="/privacy" className="cursor-target text-ink underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-tape" data-cursor-label="Privacy">
            Privacy &amp; worker safety
          </Link>
        </p>
      </div>
      <Dashboard />
    </main>
  )
}
