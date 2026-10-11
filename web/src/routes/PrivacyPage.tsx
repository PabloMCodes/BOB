import { Link } from 'react-router-dom'
import { workerPolicy } from '../data/privacy.ts'

export function PrivacyPage() {
  return (
    <main className="page-inset min-h-svh pb-20 pt-28 md:pt-36">
      <div className="mx-auto max-w-5xl">
        <p className="eyebrow text-muted">Privacy / Site policy</p>
        <h1 className="chapter-title mt-6 max-w-none text-ink">{workerPolicy.title}</h1>
        <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted">{workerPolicy.introduction}</p>
        <p className="mt-6 text-xs text-muted">
          Version 1 · Updated <time dateTime={workerPolicy.updatedDate}>{workerPolicy.updated}</time>
        </p>

        <dl className="mt-12 grid gap-6 border-y border-line py-8 sm:grid-cols-3">
          {workerPolicy.summary.map((item) => (
            <div key={item.label}>
              <dt className="text-xs leading-relaxed text-muted">{item.label}</dt>
              <dd className="mt-3 text-2xl font-medium tracking-tight text-ink">{item.value}</dd>
            </div>
          ))}
        </dl>

        <section className="mt-14" aria-labelledby="retention-heading">
          <h2 id="retention-heading" className="step-title text-ink">Image retention.</h2>
          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-left text-sm leading-relaxed">
              <caption className="sr-only">Maximum image retention periods and exceptions</caption>
              <thead className="text-xs text-muted">
                <tr>
                  <th scope="col" className="pb-4 pr-6 font-medium">Image use</th>
                  <th scope="col" className="pb-4 pr-6 font-medium">Limit</th>
                  <th scope="col" className="pb-4 font-medium">Required action</th>
                </tr>
              </thead>
              <tbody>
                {workerPolicy.retention.map((item) => (
                  <tr key={item.category} className="border-t border-line align-top">
                    <th scope="row" className="min-w-32 py-5 pr-6 font-medium text-ink">{item.category}</th>
                    <td className="min-w-28 py-5 pr-6 text-ink">{item.period}</td>
                    <td className="min-w-48 py-5 text-muted">{item.instruction}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-muted">{workerPolicy.retentionNote}</p>
          <div className="mt-6 rounded-lg border border-line bg-plate p-6">
            <h3 className="text-sm font-medium text-ink">How deletion works today</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted">{workerPolicy.implementation}</p>
          </div>
        </section>

        {workerPolicy.sections.map((section) => (
          <section key={section.id} className="mt-14 border-t border-line pt-8" aria-labelledby={`${section.id}-heading`}>
            <h2 id={`${section.id}-heading`} className="step-title text-ink">{section.title}</h2>
            {section.paragraphs.map((paragraph) => (
              <p key={paragraph} className="mt-5 max-w-3xl text-base leading-relaxed text-muted">{paragraph}</p>
            ))}
          </section>
        ))}

        <footer className="mt-14 border-t border-line pt-8">
          <p className="max-w-3xl text-sm leading-relaxed text-muted">{workerPolicy.responsibility}</p>
          <p className="eyebrow mt-8 text-muted">Guidance informing this policy</p>
          <ul className="mt-4 space-y-3">
            {workerPolicy.sources.map((source) => (
              <li key={source.href}>
                <a href={source.href} target="_blank" rel="noopener noreferrer" className="cursor-target text-sm text-muted underline decoration-line underline-offset-4 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-tape" data-cursor-label="Read">
                  {source.label}
                </a>
              </li>
            ))}
          </ul>
          <Link to="/" className="cursor-target mt-10 inline-block text-sm text-ink underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-tape" data-cursor-label="Home">Back to B.O.B</Link>
        </footer>
      </div>
    </main>
  )
}
