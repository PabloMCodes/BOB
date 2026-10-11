import { StatusBoard } from '../components/StatusBoard.tsx'
import { statusPage } from '../data/status.ts'

export function StatusPage() {
  return (
    <main className="page-inset min-h-svh pb-32 pt-28">
      {/* Header and photo share a row so the content starts above the fold. */}
      <div className="grid items-end gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)] lg:gap-16">
        <div>
          <p className="eyebrow text-muted">{statusPage.eyebrow}</p>
          <h1 className="chapter-title mt-6 text-ink">{statusPage.title}</h1>
          <p className="label-type mt-8 text-muted">{statusPage.updated}</p>
        </div>
        <figure className="max-w-[18rem] justify-self-start lg:justify-self-end">
          <img
            src={statusPage.heroPhoto.src}
            alt={statusPage.heroPhoto.alt}
            className="w-full rounded-sm object-cover"
          />
          <figcaption className="card-copy mt-3 text-muted">{statusPage.heroPhoto.caption}</figcaption>
        </figure>
      </div>
      <StatusBoard />
    </main>
  )
}
