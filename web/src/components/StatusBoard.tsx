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
      <figcaption className="card-copy mt-4 text-muted">{photo.caption}</figcaption>
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
    <section className="border-t border-line pt-14 md:pt-20">
      <Reveal>
        <p className="eyebrow text-muted">{section.eyebrow}</p>
        <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={section.eyebrow}>
          {section.title}
        </h2>
        <p className="body-copy mt-8 max-w-[46rem] text-muted">{section.summary}</p>
      </Reveal>

      <Reveal delay={80}>
        <ul className="mt-12 grid gap-x-12 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          {section.components.map((component) => (
            <li key={component.name} className="border-t border-line pt-4">
              <p className="label-type text-ink">{component.name}</p>
              <p className="card-copy mt-2 text-muted">{component.note}</p>
            </li>
          ))}
        </ul>
      </Reveal>

      {section.photos ? (
        <Reveal delay={120}>
          <div
            className={`mt-14 grid gap-10 ${section.photos.length > 1 ? 'md:grid-cols-2' : 'max-w-[46rem]'}`}
          >
            {section.photos.map((photo) => (
              <Photo key={photo.src} photo={photo} />
            ))}
          </div>
        </Reveal>
      ) : null}

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
          <p className="eyebrow text-muted">{statusPage.next.eyebrow}</p>
          <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={statusPage.next.eyebrow}>
            {statusPage.next.title}
          </h2>
        </Reveal>
        <ol className="mt-14 grid gap-x-16 gap-y-12 md:grid-cols-2">
          {statusPage.next.items.map((item, index) => (
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
    </>
  )
}
