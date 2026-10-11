import { copy } from '../data/copy.ts'
import { Reveal } from './Reveal.tsx'

export function Audience() {
  return (
    <section className="page-inset py-24 md:py-32">
      <Reveal>
        <p className="eyebrow text-muted">{copy.audience.eyebrow}</p>
        <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={copy.audience.eyebrow}>
          {copy.audience.title}
        </h2>
      </Reveal>
      <ul className="mt-16 grid gap-x-16 gap-y-12 md:grid-cols-2">
        {copy.audience.tiles.map((tile, index) => (
          <li key={tile.title}>
            <Reveal delay={index * 80} className="border-t border-line pt-6">
              <h3 className="step-title text-ink">{tile.title}</h3>
              <p className="body-copy mt-3 text-muted">{tile.body}</p>
            </Reveal>
          </li>
        ))}
      </ul>
    </section>
  )
}
