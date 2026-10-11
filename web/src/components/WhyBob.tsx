import { copy } from '../data/copy.ts'
import { Reveal } from './Reveal.tsx'

export function WhyBob() {
  const { eyebrow, title, lead, paragraphs } = copy.why

  return (
    <section className="page-inset py-24 md:py-32">
      <Reveal>
        <p className="eyebrow text-muted">{eyebrow}</p>
        <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={eyebrow}>
          {title}
        </h2>
      </Reveal>

      <Reveal delay={80} className="mt-12 max-w-[46rem] border-t border-line pt-8">
        <p className="statement text-ink">{lead}</p>
      </Reveal>

      <div className="mt-14 grid gap-x-16 gap-y-10 md:grid-cols-2">
        {paragraphs.map((paragraph, index) => (
          <Reveal key={index} delay={index * 80}>
            <p className="body-copy text-muted">{paragraph}</p>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
