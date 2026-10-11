import { copy } from '../data/copy.ts'
import { Reveal } from './Reveal.tsx'

export function Targets() {
  const { eyebrow, title, items } = copy.targets

  return (
    <section className="page-inset py-24 md:py-32">
      <Reveal>
        <p className="eyebrow text-muted">{eyebrow}</p>
        <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={eyebrow}>
          {title}
        </h2>
      </Reveal>
      <ol className="mt-16 grid gap-12 lg:grid-cols-3 lg:gap-10">
        {items.map((item, index) => (
          <li key={item.index}>
            <Reveal delay={index * 80} className="border-t border-line pt-6">
              <span className="label-type text-muted">{item.index}</span>
              <h3 className="step-title mt-5 text-ink">{item.title}</h3>
              <p className="body-copy mt-4 text-muted">{item.body}</p>
            </Reveal>
          </li>
        ))}
      </ol>
    </section>
  )
}
