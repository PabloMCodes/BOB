import { useRef } from 'react'
import { motion, useScroll, useTransform } from 'motion/react'
import { copy } from '../data/copy.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'

export function VideoSection() {
  const frame = useRef<HTMLDivElement>(null)
  const reduced = useReduced()
  const { scrollYProgress } = useScroll({ target: frame, offset: ['start end', 'center center'] })
  const scale = useTransform(scrollYProgress, [0, 1], [0.92, 1])
  const radius = useTransform(scrollYProgress, [0, 1], [28, 16])
  const id = copy.video.youtubeId.trim()

  return (
    <section className="page-inset py-16 md:py-24" aria-label={copy.video.title}>
      <motion.div
        ref={frame}
        className="relative aspect-video w-full overflow-hidden border border-line bg-plate"
        style={reduced ? { borderRadius: 16 } : { scale, borderRadius: radius }}
      >
        {id ? (
          <iframe
            className="absolute inset-0 h-full w-full"
            src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?rel=0`}
            title={copy.video.title}
            allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="label-type text-muted">{copy.video.empty}</p>
          </div>
        )}
      </motion.div>
    </section>
  )
}
