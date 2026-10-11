import { useRef } from 'react'
import { motion, useScroll, useTransform } from 'motion/react'
import { copy } from '../data/copy.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { Reveal } from './Reveal.tsx'

type Step = (typeof copy.agents.steps)[number]

function StepRow({ step, reduced }: { step: Step; reduced: boolean }) {
  const row = useRef<HTMLLIElement>(null)
  const { scrollYProgress } = useScroll({ target: row, offset: ['start 0.8', 'end 0.2'] })
  const opacity = useTransform(scrollYProgress, [0, 0.2, 0.8, 1], [0.35, 1, 1, 0.35])

  return (
    <motion.li ref={row} className="py-10" style={reduced ? undefined : { opacity }}>
      <p className="label-type text-muted">{step.index}</p>
      <h3 className="step-title mt-4 text-ink">{step.title}</h3>
      <p className="body-copy mt-4 text-muted">{step.body}</p>
    </motion.li>
  )
}

export function AgentChapter() {
  const list = useRef<HTMLOListElement>(null)
  const reduced = useReduced()
  const { scrollYProgress } = useScroll({ target: list, offset: ['start 0.6', 'end 0.6'] })

  return (
    <section className="page-inset grid gap-12 py-24 md:py-32 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-20">
      <div>
        <Reveal className="lg:sticky lg:top-32">
          <p className="eyebrow text-muted">{copy.agents.eyebrow}</p>
          <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={copy.agents.eyebrow}>
            {copy.agents.title}
          </h2>
        </Reveal>
      </div>
      <div className="relative pl-8">
        <span aria-hidden="true" className="absolute top-0 bottom-0 left-0 w-px bg-line" />
        <motion.span
          aria-hidden="true"
          className="absolute top-0 bottom-0 left-0 w-px origin-top bg-ink"
          style={reduced ? undefined : { scaleY: scrollYProgress }}
        />
        <ol ref={list}>
          {copy.agents.steps.map((step) => (
            <StepRow key={step.index} step={step} reduced={reduced} />
          ))}
        </ol>
      </div>
    </section>
  )
}
