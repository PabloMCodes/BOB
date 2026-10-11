import { useEffect, useRef, useState } from 'react'
import { motion, useInView, type MotionValue } from 'motion/react'
import type { Status } from '../data/copy.ts'
import type { LookBox, Media } from '../data/media.ts'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { StatusTag } from './StatusTag.tsx'

const FRAME_ASPECT = 4 / 5
const DRIFT_WIDTH = 1.08

function Boxes({ boxes }: { boxes: LookBox[] }) {
  const reduced = useReduced()
  return (
    <>
      {boxes.map((box, index) => (
        <motion.span
          key={`${box.label}-${index}`}
          className="look-box"
          style={{
            left: `${box.x * 100}%`,
            top: `${box.y * 100}%`,
            width: `${box.w * 100}%`,
            height: `${box.h * 100}%`,
          }}
          initial={reduced ? false : { opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, amount: 0.5 }}
          transition={{ duration: 0.4, delay: 0.2 + index * 0.12 }}
        >
          <span className="look-label">{box.label}</span>
        </motion.span>
      ))}
    </>
  )
}

function CardImage({ media }: { media: Media }) {
  const boxes = media.boxes ?? []
  const img = useRef<HTMLImageElement>(null)
  const [aspect, setAspect] = useState<number | null>(null)

  useEffect(() => {
    const node = img.current
    if (node?.complete && node.naturalWidth > 0) setAspect(node.naturalWidth / node.naturalHeight)
  }, [])

  const onLoad = () => {
    const node = img.current
    if (node && node.naturalWidth > 0) setAspect(node.naturalWidth / node.naturalHeight)
  }

  if (boxes.length === 0 || aspect === null) {
    return (
      <img
        ref={img}
        src={media.src}
        alt={media.alt}
        onLoad={onLoad}
        className="absolute inset-0 h-full w-full object-cover"
      />
    )
  }

  // Keep the photo at its own aspect so measured boxes stay on their pixels; the frame crops it.
  const wider = aspect >= FRAME_ASPECT * DRIFT_WIDTH
  return (
    <div
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
      style={wider ? { height: '100%', aspectRatio: aspect } : { width: '100%', aspectRatio: aspect }}
    >
      <img src={media.src} alt={media.alt} className="h-full w-full" />
      <Boxes boxes={boxes} />
    </div>
  )
}

function CardVideo({ media }: { media: Media }) {
  const video = useRef<HTMLVideoElement>(null)
  const inView = useInView(video, { amount: 0.3 })
  const reduced = useReduced()

  useEffect(() => {
    const node = video.current
    if (!node) return
    if (inView && !reduced) {
      node.play().catch(() => {})
    } else {
      node.pause()
    }
  }, [inView, reduced])

  return (
    <video
      ref={video}
      src={media.src}
      aria-label={media.alt}
      className="absolute inset-0 h-full w-full object-cover"
      muted
      loop
      playsInline
      preload="metadata"
    />
  )
}

type SkillCardProps = {
  index: number
  status: Status
  title: string
  body: string
  media?: Media
  drift?: MotionValue<string>
}

export function SkillCard({ index, status, title, body, media, drift }: SkillCardProps) {
  return (
    <article className="w-(--card-w) shrink-0 overflow-hidden rounded-[1.25rem] border border-band-line bg-card shadow-[0_1px_2px_rgb(0_0_0/0.04),0_12px_32px_-16px_rgb(0_0_0/0.18)] max-lg:w-[min(80vw,22rem)]">
      <div className="relative aspect-[4/5] overflow-hidden bg-band-plate">
        {media ? (
          <motion.div
            className="absolute inset-y-0 -left-[4%] w-[108%]"
            style={drift ? { x: drift } : undefined}
          >
            {media.kind === 'video' ? <CardVideo media={media} /> : <CardImage media={media} />}
          </motion.div>
        ) : (
          <p className="label-type absolute bottom-4 left-4 text-band-muted">
            {String(index + 1).padStart(2, '0')}
          </p>
        )}
        <div className="absolute top-3 left-3">
          <StatusTag status={status} tone="chip" />
        </div>
      </div>
      <div className="px-5 pt-5 pb-8">
        <h3 className="card-title text-band-ink">{title}</h3>
        <p className="card-copy mt-2.5 text-band-muted">{body}</p>
      </div>
    </article>
  )
}
