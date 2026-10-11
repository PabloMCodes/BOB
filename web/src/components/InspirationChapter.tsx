import { useRef } from 'react'
import { motion, useScroll, useTransform } from 'motion/react'
import type { JourneyChapter } from '../data/inspiration.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { EASE } from './motion.ts'

export function InspirationChapter({ chapter, index }: { chapter: JourneyChapter; index: number }) {
  const section = useRef<HTMLElement>(null)
  const reduced = useReduced()
  const { scrollYProgress } = useScroll({ target: section, offset: ['start end', 'end start'] })
  // The photo stays inside its frame, including at either end of its travel.
  const photoY = useTransform(scrollYProgress, [0, 1], ['-2%', '2%'])
  const photoScale = useTransform(scrollYProgress, [0, 0.5, 1], [0.95, 1, 0.95])

  return (
    <section ref={section} aria-labelledby={`${chapter.id}-heading`} className="relative min-w-0 border-t border-line pt-6">
      <motion.span
        aria-hidden="true"
        className="absolute -top-px left-0 h-px w-full origin-left bg-ink/50"
        initial={reduced ? false : { scaleX: 0 }}
        animate={reduced ? { scaleX: 1 } : undefined}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: true, amount: 0.2 }}
        transition={{ duration: reduced ? 0 : 0.9, ease: EASE }}
      />
      <motion.div
        initial={reduced ? false : { opacity: 0, y: 32 }}
        animate={reduced ? { opacity: 1, y: 0 } : undefined}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.2 }}
        transition={{ duration: reduced ? 0 : 0.7, ease: EASE }}
      >
        <div className="flex items-start gap-5">
          <span className="label-type pt-1 text-muted">{String(index + 1).padStart(2, '0')}</span>
          <h3 id={`${chapter.id}-heading`} className="step-title">{chapter.title}</h3>
        </div>
        {chapter.story ? (
          <p className="mt-5 min-h-24 max-w-xl text-sm leading-relaxed text-muted">{chapter.story}</p>
        ) : (
          <div className="mt-5 min-h-24 border-l border-dashed border-line pl-5">
            <p className="text-sm text-muted">This part of our story is coming soon.</p>
            <p className="mt-2 text-xs leading-relaxed text-muted">{chapter.storyPrompt}</p>
          </div>
        )}
      </motion.div>
      <motion.figure
        className="mt-6 min-w-0"
        initial={reduced ? false : { opacity: 0, y: 40 }}
        animate={reduced ? { opacity: 1, y: 0 } : undefined}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.15 }}
        transition={{ duration: reduced ? 0 : 0.8, ease: EASE }}
      >
        <div className={`journey-image-box ${chapter.photo.src ? 'border-line' : 'border-dashed border-line'}`}>
          {chapter.photo.src ? (
            <motion.img
              src={chapter.photo.src}
              alt={chapter.photo.alt}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-contain"
              style={reduced ? { y: 0, scale: 1 } : { y: photoY, scale: photoScale }}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center text-muted">
              <svg viewBox="0 0 32 32" className="size-8" fill="none" stroke="currentColor" strokeWidth="1" aria-hidden="true"><rect x="3" y="5" width="26" height="22" rx="2" /><circle cx="11" cy="12" r="2.5" /><path d="m4 24 9-8 6 5 4-4 6 7" /></svg>
              <span className="text-sm">Photo to come</span>
            </div>
          )}
        </div>
        <figcaption className="mt-3 text-xs leading-relaxed text-muted">{chapter.photo.caption}</figcaption>
      </motion.figure>
      {chapter.teamwork ? (
        <motion.div
          className="mt-7 grid gap-5 rounded-xl border border-line bg-plate/40 p-5 sm:grid-cols-2"
          initial={reduced ? false : 'hidden'}
          animate={reduced ? 'shown' : undefined}
          whileInView="shown"
          viewport={{ once: true, amount: 0.15 }}
          variants={{ hidden: {}, shown: { transition: { staggerChildren: reduced ? 0 : 0.16 } } }}
        >
          <motion.div variants={{ hidden: { opacity: 0, y: 24 }, shown: { opacity: 1, y: 0, transition: { duration: reduced ? 0 : 0.7, ease: EASE } } }}>
            <p className="eyebrow text-muted">The challenge</p>
            <p className="mt-3 text-sm leading-relaxed text-ink">{chapter.teamwork.challenge}</p>
          </motion.div>
          <motion.div className="border-t border-line pt-5 sm:border-t-0 sm:border-l sm:pt-0 sm:pl-5" variants={{ hidden: { opacity: 0, y: 24 }, shown: { opacity: 1, y: 0, transition: { duration: reduced ? 0 : 0.7, ease: EASE } } }}>
            <p className="eyebrow text-muted">How we worked through it</p>
            {chapter.teamwork.responseStatus === 'draft' && <span className="mt-2 inline-block rounded border border-line px-2 py-1 text-[0.65rem] uppercase tracking-wider text-muted">Draft team notes</span>}
            <p className="mt-3 text-sm leading-relaxed text-muted">{chapter.teamwork.response}</p>
          </motion.div>
        </motion.div>
      ) : null}
    </section>
  )
}
