import { useRef } from 'react'
import { motion, useScroll, useTransform, type MotionValue } from 'motion/react'
import { copy } from '../data/copy.ts'
import { useMediaQuery, useReduced, WIDE_QUERY } from '../hooks/useMediaQuery.ts'
import { Reveal } from './Reveal.tsx'
import { StatusTag } from './StatusTag.tsx'

const INK = 'var(--color-ink)'
const MUTED = 'var(--color-muted)'

function NodeIndex({
  index,
  progress,
  threshold,
}: {
  index: string
  progress: MotionValue<number>
  threshold: number
}) {
  const color = useTransform(progress, (value) => (value >= threshold ? INK : MUTED))
  const dot = useTransform(progress, (value) => (value >= threshold ? INK : 'var(--color-canvas)'))
  return (
    <div className="flex items-center gap-3">
      <motion.span
        className="relative z-10 block size-[15px] rounded-full border border-ink"
        style={{ backgroundColor: dot }}
      />
      <motion.span className="label-type" style={{ color }}>
        {index}
      </motion.span>
    </div>
  )
}

export function SystemLine() {
  const list = useRef<HTMLOListElement>(null)
  const wide = useMediaQuery(WIDE_QUERY)
  const reduced = useReduced()
  const { scrollYProgress } = useScroll({ target: list, offset: ['start 0.8', 'end 0.5'] })
  const nodes = copy.system.nodes
  const fill = reduced ? undefined : scrollYProgress

  return (
    <section className="page-inset py-24 md:py-32">
      <Reveal>
        <p className="eyebrow text-muted">{copy.system.eyebrow}</p>
        <h2 className="chapter-title cursor-target mt-6 w-fit text-ink" data-cursor-label={copy.system.eyebrow}>
          {copy.system.title}
        </h2>
      </Reveal>
      <ol ref={list} className="relative mt-16 grid gap-14 lg:grid-cols-3 lg:gap-12">
        <span
          aria-hidden="true"
          className="absolute bg-line max-lg:top-0 max-lg:bottom-0 max-lg:left-[7px] max-lg:w-px lg:top-[7px] lg:right-0 lg:left-0 lg:h-px"
        />
        <motion.span
          aria-hidden="true"
          className="absolute bg-ink max-lg:top-0 max-lg:bottom-0 max-lg:left-[7px] max-lg:w-px max-lg:origin-top lg:top-[7px] lg:right-0 lg:left-0 lg:h-px lg:origin-left"
          style={fill ? (wide ? { scaleX: fill } : { scaleY: fill }) : undefined}
        />
        {nodes.map((node, index) => (
          <li key={node.index} className="relative max-lg:pl-0">
            <NodeIndex
              index={node.index}
              progress={fill ?? scrollYProgress}
              threshold={reduced ? -1 : (index / nodes.length) * 0.95}
            />
            <Reveal delay={index * 80} className="mt-6 max-lg:pl-8">
              <h3 className="step-title text-ink">{node.title}</h3>
              <p className="body-copy mt-3 text-muted">{node.body}</p>
              <div className="mt-5">
                <StatusTag status={node.status} tone="dark" />
              </div>
            </Reveal>
          </li>
        ))}
      </ol>
    </section>
  )
}
