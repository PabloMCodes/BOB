import { useRef } from 'react'
import { motion, useScroll, useSpring, useTransform } from 'motion/react'
import { Link } from 'react-router-dom'
import { Credits } from '../components/Credits.tsx'
import { InspirationChapter } from '../components/InspirationChapter.tsx'
import { InspirationTitle } from '../components/InspirationTitle.tsx'
import { OriginsGlobe } from '../components/OriginsGlobe.tsx'
import { Reveal } from '../components/Reveal.tsx'
import { TeamConvergence } from '../components/TeamConvergence.tsx'
import { copy } from '../data/copy.ts'
import { inspirationChapters } from '../data/inspiration.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'

export function InspirationPage() {
  const page = useRef<HTMLElement>(null)
  const intro = useRef<HTMLDivElement>(null)
  const reduced = useReduced()
  const { scrollYProgress: pageProgress } = useScroll({ target: page, offset: ['start start', 'end end'] })
  const readingProgress = useSpring(pageProgress, { stiffness: 120, damping: 30, restDelta: 0.001 })
  const { scrollYProgress: introProgress } = useScroll({ target: intro, offset: ['start start', 'end start'] })
  const introY = useTransform(introProgress, [0, 1], [0, -60])
  const introOpacity = useTransform(introProgress, [0, 1], [1, 0.6])

  return (
    <>
      {!reduced && <motion.div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-16 z-30 h-px origin-left bg-ink/70" style={{ scaleX: readingProgress }} />}
      <main ref={page} className="page-inset pb-24 pt-32 md:pt-40">
        <div className="mx-auto max-w-7xl">
          <div ref={intro}>
            <motion.div style={reduced ? { y: 0, opacity: 1 } : { y: introY, opacity: introOpacity }}>
              <Reveal>
                <p className="eyebrow text-muted">Inspiration / The story so far</p>
              </Reveal>
              <InspirationTitle as="h1" lines={['Different beginnings.', 'Built together.']} className="inspiration-title mt-7 max-w-5xl" />
              <Reveal delay={200}>
                <p className="body-copy mt-8 text-muted">The people, decisions and setbacks behind the rover on our workbench. A growing record of what we built and how we worked through it together.</p>
                <a href="#build-story" className="cursor-target mt-8 inline-flex items-center gap-3 text-sm text-ink underline decoration-line underline-offset-8 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink" data-cursor-label="Explore">Follow the build <span aria-hidden="true">↘</span></a>
              </Reveal>
              {/* The statements the product hero opens with, kept here in the same type so the story starts from what B.O.B is. */}
              <div className="mt-16 grid gap-8 border-t border-line pt-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-end lg:gap-16">
                <Reveal delay={280}>
                  <p className="hero-title text-ink">{copy.hero.title}</p>
                </Reveal>
                <Reveal delay={360}>
                  <p className="body-copy text-muted">{copy.hero.body}</p>
                </Reveal>
              </div>
            </motion.div>
          </div>

          <section id="build-story" className="mt-24 scroll-mt-24 border-t border-line pt-10" aria-labelledby="journey-heading">
            <Reveal>
              <p className="eyebrow text-muted">01 / From idea to rover</p>
              <h2 id="journey-heading" className="chapter-title mt-5 max-w-none">Built one piece at a time.</h2>
              <p className="mt-5 max-w-xl text-muted">The parts that came together, the setbacks along the way, and the team behind every next step.</p>
            </Reveal>
            <div className="mt-14 grid gap-x-10 gap-y-16 lg:grid-cols-2">
              {inspirationChapters.map((chapter, index) => (
                <InspirationChapter key={chapter.id} chapter={chapter} index={index} />
              ))}
            </div>
            <div className="mt-20 flex flex-col gap-5 border-t border-line pt-8 sm:flex-row sm:items-center sm:justify-between">
              <p className="max-w-lg text-sm leading-relaxed text-muted">The story continues as the rover takes shape. More sketches, build photos and test notes will live here.</p>
              <Link to="/" className="cursor-target shrink-0 text-sm underline decoration-line underline-offset-8 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink" data-cursor-label="Product">Explore B.O.B <span aria-hidden="true">↗</span></Link>
            </div>
          </section>
          <section id="our-origins" className="scroll-mt-24 mt-24 border-t border-line pt-10 md:mt-32" aria-labelledby="origins-heading">
            <Reveal className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="eyebrow text-muted">02 / Our origins</p>
                <h2 id="origins-heading" className="chapter-title mt-5 max-w-none">Three countries.<br />One shared build.</h2>
              </div>
              <p className="max-w-sm text-sm leading-relaxed text-muted">Our roots reach back to Mexico, Venezuela and Pakistan. The connections meet in Florida, where this project comes together.</p>
            </Reveal>
            <TeamConvergence />
            <OriginsGlobe />
          </section>

        </div>
      </main>
      <Credits />
    </>
  )
}
