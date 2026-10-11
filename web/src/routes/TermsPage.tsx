import { Link } from 'react-router-dom'
import { serviceTerms } from '../data/terms.ts'

const linkClass = 'cursor-target text-sm text-ink underline decoration-line underline-offset-4 hover:decoration-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-tape'

export function TermsPage() {
  return (
    <main className="page-inset min-h-svh pb-20 pt-28 md:pt-36">
      <div className="mx-auto max-w-5xl">
        <p className="eyebrow text-muted">Terms / Prototype use</p>
        <h1 className="chapter-title mt-6 max-w-none text-ink">{serviceTerms.title}</h1>
        <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted">{serviceTerms.introduction}</p>
        <p className="mt-6 text-xs text-muted">
          Version 1 · Updated <time dateTime={serviceTerms.updatedDate}>{serviceTerms.updated}</time>
        </p>

        <dl className="mt-10 grid gap-6 border-y border-line py-8 sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted">Service operator</dt>
            <dd className="mt-3 text-base text-ink">{serviceTerms.organization}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Contact</dt>
            <dd className="mt-3 break-words"><a className={linkClass} href={`mailto:${serviceTerms.contactEmail}`} data-cursor-label="Email">{serviceTerms.contactEmail}</a></dd>
          </div>
        </dl>

        {serviceTerms.sections.map((section) => (
          <section key={section.id} className="mt-12" aria-labelledby={`terms-${section.id}`}>
            <h2 id={`terms-${section.id}`} className="step-title text-ink">{section.title}</h2>
            {section.paragraphs.map((paragraph) => (
              <p key={paragraph} className="mt-5 max-w-3xl text-base leading-relaxed text-muted">{paragraph}</p>
            ))}
            {section.id === 'worker-data' && <Link to="/privacy" className={`${linkClass} mt-5 inline-block`} data-cursor-label="Privacy">Read the worker privacy &amp; safety policy</Link>}
          </section>
        ))}

        <footer className="mt-14 border-t border-line pt-8">
          <p className="eyebrow text-muted">Licenses and safety guidance</p>
          <ul className="mt-5 space-y-3">
            {serviceTerms.references.map((reference) => (
              <li key={reference.href}><a className={linkClass} href={reference.href} target="_blank" rel="noopener noreferrer" data-cursor-label="Read">{reference.label}</a></li>
            ))}
          </ul>
          <div className="mt-10 flex flex-wrap gap-6">
            <Link to="/" className={linkClass} data-cursor-label="Home">Back to B.O.B</Link>
            <Link to="/privacy" className={linkClass} data-cursor-label="Privacy">Privacy &amp; worker safety</Link>
          </div>
        </footer>
      </div>
    </main>
  )
}
