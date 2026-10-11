import { motion } from 'motion/react'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { EASE } from './motion.ts'

/** One readable heading for assistive technology; words share one entrance trigger. */
export function InspirationTitle({ lines, as = 'h2', className = '' }: { lines: string[]; as?: 'h1' | 'h2'; className?: string }) {
  const reduced = useReduced()
  const Heading = as === 'h1' ? motion.h1 : motion.h2
  return (
    <Heading
      className={className}
      initial={reduced ? false : 'hidden'}
      animate={reduced ? 'shown' : undefined}
      whileInView="shown"
      viewport={{ once: true, amount: 0.2 }}
      variants={{ hidden: {}, shown: { transition: { staggerChildren: reduced ? 0 : 0.09 } } }}
    >
      <span className="sr-only">{lines.join(' ')}</span>
      {lines.map((line, lineIndex) => (
        <span key={line} aria-hidden="true" className={`flex flex-wrap gap-x-[0.2em] ${lineIndex > 0 ? 'text-muted' : ''}`}>
          {line.split(' ').map((word, wordIndex) => (
            <span key={`${word}-${wordIndex}`} className="-mb-[0.12em] inline-block overflow-hidden pb-[0.12em]">
              <motion.span
                className="inline-block"
                variants={{
                  hidden: { y: '110%', rotate: 3 },
                  shown: { y: 0, rotate: 0, transition: { duration: reduced ? 0 : 0.95, ease: EASE } },
                }}
              >{word}</motion.span>
            </span>
          ))}
        </span>
      ))}
    </Heading>
  )
}
