import { useLayoutEffect, useRef, useState } from 'react'
import { motion, useScroll, useTransform } from 'motion/react'
import { copy } from '../data/copy.ts'
import { skillMedia } from '../data/media.ts'
import { usePinned } from '../hooks/useMediaQuery.ts'
import { Reveal } from './Reveal.tsx'
import { SkillCard } from './SkillCard.tsx'

const SCROLL_FACTOR = 1.85
const HOLD = 0.22

type Geometry = { maxOffset: number; hold: number }

function Heading() {
  return (
    <Reveal>
      <p className="eyebrow text-band-muted">{copy.skills.eyebrow}</p>
      <h2 className="chapter-title cursor-target mt-4 w-fit max-w-none text-band-ink" data-cursor-label={copy.skills.eyebrow}>
        {copy.skills.title}
      </h2>
    </Reveal>
  )
}

function PinnedRail() {
  const rail = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const track = useRef<HTMLDivElement>(null)
  const geometry = useRef<Geometry>({ maxOffset: 0, hold: 0 })
  const [height, setHeight] = useState<number | undefined>(undefined)

  useLayoutEffect(() => {
    const measure = () => {
      const trackNode = track.current
      const frameNode = frame.current
      if (!trackNode || !frameNode) return
      const maxOffset = Math.max(trackNode.scrollWidth - frameNode.clientWidth, 0)
      const hold = Math.round(window.innerHeight * HOLD)
      geometry.current = { maxOffset, hold }
      setHeight(window.innerHeight + hold + maxOffset * SCROLL_FACTOR)
    }
    measure()
    const observer = new ResizeObserver(measure)
    if (track.current) observer.observe(track.current)
    window.addEventListener('resize', measure)
    document.fonts?.ready.then(measure).catch(() => {})
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])

  const { scrollYProgress } = useScroll({ target: rail, offset: ['start start', 'end end'] })
  const offset = useTransform(scrollYProgress, (progress) => {
    const { maxOffset, hold } = geometry.current
    const scrolled = progress * (hold + maxOffset * SCROLL_FACTOR)
    return Math.min(Math.max((scrolled - hold) / SCROLL_FACTOR, 0), maxOffset)
  })
  const x = useTransform(offset, (value) => -value)
  const leftFade = useTransform(offset, (value) => (value > 2 ? 1 : 0))
  const rightFade = useTransform(offset, (value) =>
    value < geometry.current.maxOffset - 2 ? 1 : 0,
  )
  const drift = useTransform(scrollYProgress, [0, 1], ['-3.5%', '3.5%'])

  return (
    <section className="skills-band bg-band">
      <div className="page-inset pt-24 md:pt-32">
        <div className="skills-frame">
          <Heading />
        </div>
      </div>
      <div ref={rail} className="relative" style={{ height }}>
        <div className="sticky top-0 flex h-svh items-center pt-16">
          <div className="page-inset w-full">
            <div ref={frame} className="skills-frame relative -my-10 overflow-hidden py-10">
              <motion.div className="rail-fade-left" style={{ opacity: leftFade }} />
              <motion.div className="rail-fade-right" style={{ opacity: rightFade }} />
              <motion.div ref={track} className="flex w-max gap-(--card-gap)" style={{ x }}>
                {copy.skills.cards.map((card, index) => (
                  <SkillCard
                    key={card.id}
                    index={index}
                    status={card.status}
                    title={card.title}
                    body={card.body}
                    media={skillMedia[card.id]}
                    drift={drift}
                  />
                ))}
              </motion.div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function SwipeRail() {
  return (
    <section className="skills-band bg-band py-20">
      <div className="page-inset">
        <Heading />
      </div>
      <div
        className="snap-rail page-inset mt-10 flex gap-4 overflow-x-auto pb-2"
        style={{ scrollPaddingLeft: 'clamp(1.25rem, 4vw, 4.5rem)' }}
      >
        {copy.skills.cards.map((card, index) => (
          <SkillCard
            key={card.id}
            index={index}
            status={card.status}
            title={card.title}
            body={card.body}
            media={skillMedia[card.id]}
          />
        ))}
      </div>
    </section>
  )
}

export function SkillsRail() {
  return usePinned() ? <PinnedRail /> : <SwipeRail />
}
