import { useRef } from 'react'
import { motion, useScroll, useTransform, type MotionValue } from 'motion/react'
import { copy } from '../data/copy.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { Reveal } from './Reveal.tsx'

function Word({
  word,
  progress,
  range,
}: {
  word: string
  progress: MotionValue<number>
  range: [number, number]
}) {
  const opacity = useTransform(progress, range, [0.2, 1])
  return <motion.span style={{ opacity }}>{word} </motion.span>
}

export function Overview() {
  const paragraph = useRef<HTMLParagraphElement>(null)
  const reduced = useReduced()
  const { scrollYProgress } = useScroll({ target: paragraph, offset: ['start 0.85', 'end 0.35'] })
  const words = copy.overview.statement.split(' ')

  return (
    <section className="page-inset py-24 md:py-36">
      <Reveal>
        <p className="eyebrow text-muted">{copy.overview.eyebrow}</p>
      </Reveal>
      <p ref={paragraph} className="statement mt-8 text-ink">
        {reduced
          ? copy.overview.statement
          : words.map((word, index) => (
              <Word
                key={index}
                word={word}
                progress={scrollYProgress}
                range={[index / words.length, (index + 1) / words.length]}
              />
            ))}
      </p>

      <Reveal delay={80} className="mt-20 border-t border-line pt-10 md:mt-24">
        <p className="statement max-w-[34ch] text-ink">{copy.overview.rolesLead}</p>
      </Reveal>
      <ul className="mt-14 grid gap-x-16 gap-y-12 md:grid-cols-2">
        {copy.overview.roles.map((role, index) => (
          <li key={role.label}>
            <Reveal delay={index * 80} className="border-t border-line pt-6">
              <p className="label-type text-tape">{role.label}</p>
              <h3 className="step-title mt-5 text-ink">{role.title}</h3>
              <p className="body-copy mt-4 text-muted">{role.body}</p>
            </Reveal>
          </li>
        ))}
      </ul>
    </section>
  )
}
