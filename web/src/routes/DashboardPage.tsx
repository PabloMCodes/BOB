import { copy } from '../data/copy.ts'
import { Dashboard } from '../dashboard/Dashboard.tsx'

export function DashboardPage() {
  return (
    <main className="page-inset min-h-svh pb-16 pt-28">
      <div className="twin-title">
        <p className="eyebrow text-muted">{copy.dashboard.eyebrow}</p>
        <h1 className="chapter-title mt-6 text-ink">{copy.dashboard.title}</h1>
        <p className="body-copy mt-6 text-muted">{copy.dashboard.sentence}</p>
      </div>
      <Dashboard />
    </main>
  )
}
