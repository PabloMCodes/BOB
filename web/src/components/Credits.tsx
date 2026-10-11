import { Link } from 'react-router-dom'
import { copy } from '../data/copy.ts'
import { Reveal } from './Reveal.tsx'

function ProjectLine() {
  const { text, link } = copy.credits.project
  const at = text.indexOf(link.label)
  if (at < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <a
        href={link.href}
        target="_blank"
        rel="noopener noreferrer"
        className="cursor-target text-ink underline decoration-line underline-offset-4 transition-colors hover:decoration-ink"
        data-cursor-label={link.label}
      >
        {link.label}
      </a>
      {text.slice(at + link.label.length)}
    </>
  )
}

function LinkedInMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="size-4 shrink-0 text-muted transition-colors group-hover:text-ink"
      fill="currentColor"
    >
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13ZM7.12 20.45H3.56V9h3.56v11.45ZM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z" />
    </svg>
  )
}

export function Credits() {
  const { team } = copy.credits
  return (
    <footer className="page-inset border-t border-line pt-24 pb-16 md:pt-32">
      <Reveal>
        <h2 className="chapter-title cursor-target w-fit text-ink" data-cursor-label={copy.wordmark}>
          {copy.credits.claim}
        </h2>
        <p className="body-copy mt-6 text-muted">
          <ProjectLine />
        </p>
      </Reveal>
      {team.length > 0 ? (
        <ul className="mt-14 grid gap-x-10 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          {team.map((person) => (
            <li key={person.name}>
              {person.linkedin ? (
                <>
                  <a
                    href={person.linkedin}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`${person.name} on LinkedIn`}
                    className="cursor-target group inline-flex items-center gap-2.5 text-ink"
                    data-cursor-label={person.firstName}
                  >
                    <span className="underline decoration-line underline-offset-4 transition-colors group-hover:decoration-ink">
                      {person.name}
                    </span>
                    <LinkedInMark />
                  </a>
                  {person.role ? <p className="label-type mt-1 text-muted">{person.role}</p> : null}
                </>
              ) : (
                <>
                  <p className="text-ink">{person.name}</p>
                  {person.role ? <p className="label-type mt-1 text-muted">{person.role}</p> : null}
                </>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-20 flex flex-col gap-6 border-t border-line pt-8 md:flex-row md:items-end md:justify-between">
        <div className="max-w-2xl">
          <p className="text-sm leading-relaxed text-muted">{copy.credits.license}</p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Skill photographs:{' '}
            {copy.credits.photos.map((photo, index) => (
              <span key={photo.href}>
                {index > 0 ? '; ' : ''}
                <a
                  href={photo.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline decoration-line underline-offset-4 transition-colors hover:decoration-ink"
                >
                  {photo.title}
                </a>
                {` by ${photo.author}, `}
                <a
                  href={photo.licenseHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline decoration-line underline-offset-4 transition-colors hover:decoration-ink"
                >
                  {photo.license}
                </a>
              </span>
            ))}
            . The annotated versions are derivatives under the same licence.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-6">
          <Link
            to="/privacy"
            className="cursor-target label-type text-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-tape"
            data-cursor-label="Privacy"
          >
            Privacy &amp; worker safety
          </Link>
          <Link
            to="/terms"
            className="cursor-target label-type text-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-tape"
            data-cursor-label="Terms"
          >
            Terms of Service
          </Link>
          {copy.links.github ? (
            <a
              href={copy.links.github}
              className="cursor-target label-type text-muted transition-colors hover:text-ink"
              data-cursor-label="GitHub"
              target="_blank"
              rel="noreferrer"
            >
              {copy.nav.github}
            </a>
          ) : null}
          <span className="text-[1.05rem] font-semibold tracking-[-0.02em] text-ink">
            {copy.wordmark}
          </span>
        </div>
      </div>
    </footer>
  )
}
