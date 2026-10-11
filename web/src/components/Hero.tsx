import { useRef } from 'react'
import { motion, useScroll, useTransform } from 'motion/react'
import { copy } from '../data/copy.ts'
import { heroBackground } from '../data/media.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { EASE } from './motion.ts'
import { Reveal } from './Reveal.tsx'

function Wordmark({ reduced }: { reduced: boolean }) {
  const letters = Array.from(copy.wordmark)
  return (
    <span aria-hidden="true" className="wordmark flex text-ink">
      {letters.map((letter, index) => (
        <span key={index} className="inline-block overflow-hidden pb-[0.06em]">
          <motion.span
            className="inline-block"
            initial={reduced ? false : { y: '105%' }}
            animate={{ y: 0 }}
            transition={{ duration: 0.9, ease: EASE, delay: 0.08 + index * 0.06 }}
          >
            {letter}
          </motion.span>
        </span>
      ))}
    </span>
  )
}

function Background() {
  if (!heroBackground) return <div className="hero-grid absolute inset-0" />
  if (heroBackground.kind === 'video') {
    return (
      <video
        className="absolute inset-0 h-full w-full object-cover"
        src={heroBackground.src}
        aria-label={heroBackground.alt}
        autoPlay
        muted
        loop
        playsInline
      />
    )
  }
  return (
    <img
      className="absolute inset-0 h-full w-full object-cover"
      src={heroBackground.src}
      alt={heroBackground.alt}
    />
  )
}

export function Hero() {
  const section = useRef<HTMLElement>(null)
  const reduced = useReduced()
  const { scrollYProgress } = useScroll({ target: section, offset: ['start start', 'end start'] })
  const bgY = useTransform(scrollYProgress, [0, 1], ['0%', '40%'])
  const bgScale = useTransform(scrollYProgress, [0, 1], [1, 1.08])
  const textY = useTransform(scrollYProgress, [0, 1], ['0%', '-12%'])
  const textOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0])
  const shade = useTransform(scrollYProgress, [0, 1], [0, 0.6])

  return (
    <section ref={section} className="relative min-h-svh overflow-hidden">
      <motion.div
        className="absolute inset-0 origin-top"
        style={reduced ? undefined : { y: bgY, scale: bgScale }}
      >
        <Background />
      </motion.div>
      {heroBackground ? (
        <div className="absolute inset-0 bg-linear-to-b from-canvas/35 via-canvas/55 to-canvas/85" />
      ) : null}
      <motion.div
        className="pointer-events-none absolute inset-0 bg-canvas"
        style={{ opacity: reduced ? 0 : shade }}
      />

      <motion.div
        className="page-inset relative z-10 flex min-h-svh flex-col justify-end pt-28 pb-10"
        style={reduced ? undefined : { y: textY, opacity: textOpacity }}
      >
        <h1>
          <span className="sr-only">
            {copy.wordmark}, {copy.expansion}
          </span>
          <motion.span
            aria-hidden="true"
            className="eyebrow block text-muted"
            initial={reduced ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE }}
          >
            {copy.expansion}
          </motion.span>
          <span className="mt-4 block">
            <Wordmark reduced={reduced} />
          </span>
        </h1>

        <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-end lg:gap-16">
          <Reveal delay={320}>
            <p className="hero-title text-ink">{copy.hero.title}</p>
          </Reveal>
          <Reveal delay={400}>
            <p className="body-copy text-muted">{copy.hero.body}</p>
          </Reveal>
        </div>

        <div className="mt-14 flex items-center gap-3">
          <span className="label-type text-muted">{copy.hero.scroll}</span>
          <span className="scroll-line" aria-hidden="true" />
        </div>
      </motion.div>
    </section>
  )
}
