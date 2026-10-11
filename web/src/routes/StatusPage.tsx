import { StatusBoard } from '../components/StatusBoard.tsx'
import { statusPage } from '../data/status.ts'

export function StatusPage() {
  return (
    <main className="page-inset min-h-svh pb-32 pt-28">
      <p className="eyebrow text-muted">{statusPage.eyebrow}</p>
      <h1 className="chapter-title mt-6 text-ink">{statusPage.title}</h1>
      <p className="body-copy mt-8 max-w-[44rem] text-muted">{statusPage.sentence}</p>
      <p className="label-type mt-8 text-muted">{statusPage.updated}</p>
      <figure className="mt-14 max-w-[36rem]">
        <img
          src={statusPage.heroPhoto.src}
          alt={statusPage.heroPhoto.alt}
          className="w-full rounded-sm object-cover"
        />
        <figcaption className="card-copy mt-4 text-muted">{statusPage.heroPhoto.caption}</figcaption>
      </figure>
      <StatusBoard />
    </main>
  )
}
