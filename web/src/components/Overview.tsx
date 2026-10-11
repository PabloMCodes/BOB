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
    </section>
  )
}
