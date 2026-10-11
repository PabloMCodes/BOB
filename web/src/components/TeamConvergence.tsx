import { motion } from 'motion/react'
import { teamOrigins } from '../data/inspiration.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { EASE } from './motion.ts'

/** A symbolic team signature; geographical connections belong to the globe. */
export function TeamConvergence() {
  const reduced = useReduced()
  const draw = (delay: number) => ({
    hidden: { pathLength: 0, opacity: 0 },
    shown: { pathLength: 1, opacity: 1, transition: { duration: reduced ? 0 : 1.2, delay: reduced ? 0 : delay, ease: EASE } },
  })
  return (
    <motion.div
      className="mx-auto mt-12 max-w-3xl"
      initial={reduced ? false : 'hidden'}
      animate={reduced ? 'shown' : undefined}
      whileInView="shown"
      viewport={{ once: true, amount: 0.25 }}
    >
      <div className="grid grid-cols-3 gap-3 text-center">
        {teamOrigins.map((person, index) => (
          <motion.p
            key={person.id}
            className="text-sm text-muted"
            variants={{ hidden: { opacity: 0, y: 18 }, shown: { opacity: 1, y: 0, transition: { duration: reduced ? 0 : 0.6, delay: reduced ? 0 : index * 0.1, ease: EASE } } }}
          >{person.firstName}</motion.p>
        ))}
      </div>
      <svg viewBox="0 0 900 140" className="mt-3 w-full text-ink" fill="none" aria-hidden="true">
        {teamOrigins.map((person, index) => {
          const x = (index + 0.5) * (900 / teamOrigins.length)
          return <motion.path key={person.id} d={`M ${x} 4 C ${x} 52, 450 48, 450 88`} stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" variants={draw(0.12 + index * 0.12)} />
        })}
        <motion.circle cx="450" cy="88" r="4" fill="currentColor" variants={{ hidden: { opacity: 0 }, shown: { opacity: 1, transition: { duration: reduced ? 0 : 0.3, delay: reduced ? 0 : 0.9 } } }} />
        <motion.path d="M 450 94 V 136" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" variants={draw(0.85)} />
      </svg>
      <motion.p
        className="mt-3 text-center text-3xl font-medium tracking-[-0.04em] md:text-5xl"
        variants={{ hidden: { opacity: 0, y: 16, scale: 0.92 }, shown: { opacity: 1, y: 0, scale: 1, transition: { duration: reduced ? 0 : 0.8, delay: reduced ? 0 : 1.05, ease: EASE } } }}
      >B.O.B.</motion.p>
    </motion.div>
  )
}
