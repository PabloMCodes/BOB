import { Reveal } from './Reveal.tsx'
import {
  metricPending,
  statusLevelLabel,
  statusPage,
  type StatusLevel,
  type StatusPhoto,
  type StatusSection,
} from '../data/status.ts'

function Photo({ photo }: { photo: StatusPhoto }) {
  return (
    <figure className="border-t border-line pt-4">
      <img src={photo.src} alt={photo.alt} loading="lazy" className="w-full rounded-sm object-cover" />
      <figcaption className="card-copy mt-3 text-muted">{photo.caption}</figcaption>
    </figure>
  )
}

const levelColor: Record<StatusLevel, string> = {
  working: 'text-clear',
  wired: 'text-tape',
  partial: 'text-tape',
  planned: 'text-muted',
}

function LevelTag({ level }: { level: StatusLevel }) {
  return <span className={`status-tag ${levelColor[level]}`}>{statusLevelLabel[level]}</span>
}

function Section({ section }: { section: StatusSection }) {
  return (
    <section className="pt-6">
      {/* The domain stays pinned under the nav, so a long scroll never loses which half it is in. */}
      <p className="domain-sticky text-ink">
        <span className="text-tape">{section.eyebrow}</span>
        <span className="text-muted">{section.title}</span>
      </p>

      <Reveal className="mt-12">
        <h2 className="domain-title cursor-target w-fit text-ink" data-cursor-label={section.eyebrow}>
          {section.eyebrow}
        </h2>
        <p className="step-title mt-5 text-ink">{section.title}</p>
      </Reveal>

      {/* Copy left, photo right: the right column was empty and the stacked photo made the scroll long. */}
      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)] lg:gap-16">
        <div>
          <Reveal>
            <p className="body-copy max-w-[46rem] text-muted">{section.summary}</p>
          </Reveal>
          <Reveal delay={80}>
            <ul className="mt-12 grid gap-x-12 gap-y-6 sm:grid-cols-2">
              {section.components.map((component) => (
                <li key={component.name} className="border-t border-line pt-4">
                  <p className="label-type text-ink">{component.name}</p>
                  <p className="card-copy mt-2 text-muted">{component.note}</p>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>

        {section.photos ? (
          <Reveal delay={120} className="lg:sticky lg:top-32 lg:self-start">
            <div className="grid gap-8">
              {section.photos.map((photo) => (
                <Photo key={photo.src} photo={photo} />
              ))}
            </div>
          </Reveal>
        ) : null}
      </div>

      {section.groups.map((group, groupIndex) => (
        <div key={group.title} className="mt-20 md:mt-24">
          <Reveal>
            <div className="flex flex-wrap items-center gap-4">
              <LevelTag level={group.level} />
              <h3 className="step-title text-ink">{group.title}</h3>
            </div>
            <p className="body-copy mt-4 text-muted">{group.note}</p>
          </Reveal>
          <ol className="mt-10 grid gap-10 lg:grid-cols-3 lg:gap-8">
            {group.items.map((item, index) => (
              <li key={item.title}>
                <Reveal delay={(groupIndex === 0 ? index : index + 1) * 80} className="border-t border-line pt-6">
                  <h4 className="card-title text-ink">{item.title}</h4>
                  <p className="body-copy mt-4 text-muted">{item.body}</p>
                  {item.metrics ? (
                    <dl className="mt-6 grid gap-x-8 gap-y-3 sm:grid-cols-2">
                      {item.metrics.map((metric) => (
                        <div key={metric.label} className="border-t border-line pt-3">
                          <dt className="card-copy text-muted">{metric.label}</dt>
                          <dd className={`label-type mt-2 ${metric.value ? 'text-ink' : 'text-tape'}`}>
                            {metric.value ?? metricPending}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                </Reveal>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  )
}

export function StatusBoard() {
  return (
    <>
      <div className="mt-24 flex flex-col gap-24 md:mt-32 md:gap-32">
        {statusPage.sections.map((section) => (
          <Section key={section.id} section={section} />
        ))}
      </div>

      <section className="mt-24 border-t border-line pt-14 md:mt-32 md:pt-20">
        <Reveal>
          <h2 className="domain-title cursor-target w-fit text-ink" data-cursor-label={statusPage.next.eyebrow}>
            {statusPage.next.eyebrow}
          </h2>
          <p className="statement mt-6 text-ink">{statusPage.next.title}</p>
        </Reveal>
        <ol className="mt-16 grid gap-x-16 gap-y-14 md:grid-cols-2">
          {statusPage.next.items.map((item, index) => (
            <li key={item.index}>
              <Reveal delay={index * 80} className="border-t border-line pt-6">
                <span className="label-type text-tape">{item.index}</span>
                <h3 className="card-title mt-5 text-ink md:text-[1.9rem]">{item.title}</h3>
                <p className="body-copy mt-4 text-muted">{item.body}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </section>
    </>
  )
}
