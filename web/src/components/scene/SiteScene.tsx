import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { useScroll } from 'motion/react'
import { copy } from '../../data/copy.ts'
import { usePinned, useReduced } from '../../hooks/useMediaQuery.ts'
import { Reveal } from '../Reveal.tsx'
import { Director, type OverlayRefs, type ProgressSource } from './Director.tsx'
import { palette } from './palette.ts'
import { marks, type MarkKind } from './timeline.ts'
import { World } from './World.tsx'

const markClass: Record<MarkKind, string> = {
  hazard: 'mark-hazard',
  clear: 'mark-clear',
  unverified: 'mark-unverified',
}

const dotColor: Record<MarkKind, string> = {
  hazard: 'var(--color-hazard)',
  clear: 'var(--color-clear)',
  unverified: 'var(--color-unverified)',
}

function canUseWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

function Heading({ compact }: { compact: boolean }) {
  return (
    <div className={`page-inset ${compact ? 'pt-6 pb-5' : 'pt-24 pb-8'}`}>
      <Reveal>
        <p className="eyebrow text-muted">{copy.scene.eyebrow}</p>
        <h2 className="chapter-title cursor-target mt-4 w-fit max-w-[34ch] text-ink" data-cursor-label={copy.scene.eyebrow}>
          {copy.scene.title}
        </h2>
      </Reveal>
    </div>
  )
}

function Lights() {
  return (
    <>
      <fog attach="fog" args={[palette.canvas, 20, 46]} />
      <hemisphereLight args={[palette.hemiSky, palette.hemiGround, 1.1]} />
      <directionalLight position={[-7, 6, 6]} intensity={2.4} color={palette.sun} />
      <directionalLight position={[6, 9, -4]} intensity={0.35} color={palette.hemiSky} />
      <ambientLight intensity={0.18} />
    </>
  )
}

function Frame({
  source,
  active,
}: {
  source: React.RefObject<ProgressSource>
  active: boolean
}) {
  const [supported] = useState(canUseWebGL)
  const refs = useRef<OverlayRefs>({
    labels: [],
    insetFrame: null,
    insetShade: null,
    insetBoxes: [],
    twin: null,
    twinPath: null,
    twinDots: [],
    twinRover: null,
    curtain: null,
  })

  if (!supported) {
    return <p className="body-copy page-inset pt-16 text-muted">{copy.scene.unavailable}</p>
  }
  return (
    <div className="scene-frame h-full w-full">
      <p className="sr-only">{copy.scene.description}</p>
      <Canvas
        dpr={[1, 1.5]}
        frameloop={active ? 'always' : 'demand'}
        camera={{ fov: 35, near: 0.1, far: 140, position: [9, 8.5, 14] }}
        gl={{ antialias: true, alpha: false }}
        onCreated={({ gl }) => gl.setClearColor(palette.canvas)}
        aria-hidden="true"
      >
        <Lights />
        <World />
        <Director source={source} overlay={refs} />
      </Canvas>
        <>
          <div className="scene-overlay">
            {marks.map((mark, index) => (
              <div
                key={mark.id}
                ref={(node) => {
                  refs.current.labels[index] = node
                }}
                className={`scene-label ${markClass[mark.kind]}`}
              >
                {mark.text}
              </div>
            ))}
          </div>

          <div
            ref={(node) => {
              refs.current.twin = node
            }}
            className="scene-overlay bg-canvas/55 opacity-0"
          >
            <div className="hero-grid absolute inset-0 opacity-60" />
            <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
              <polyline
                ref={(node) => {
                  refs.current.twinPath = node
                }}
                fill="none"
                stroke="var(--color-ink)"
                strokeWidth={2}
                strokeLinecap="round"
              />
              {marks.map((mark, index) => (
                <circle
                  key={mark.id}
                  ref={(node) => {
                    refs.current.twinDots[index] = node
                  }}
                  r={6}
                  fill={dotColor[mark.kind]}
                  stroke="var(--color-canvas)"
                  strokeWidth={2}
                  style={{ opacity: 0 }}
                />
              ))}
              <circle
                ref={(node) => {
                  refs.current.twinRover = node
                }}
                r={9}
                fill="none"
                stroke="var(--color-ink)"
                strokeWidth={2}
              />
            </svg>
            <div className="page-inset absolute bottom-6 left-0">
              <p className="label-type inline-block border border-tape px-2 py-1 text-tape">{copy.scene.twin}</p>
              <p className="mt-3 max-w-xs text-sm text-muted">{copy.scene.twinNote}</p>
            </div>
          </div>

          <div
            ref={(node) => {
              refs.current.insetFrame = node
            }}
            className="inset-frame pointer-events-none"
          >
            <div className="absolute inset-0 overflow-hidden">
              {marks.map((mark, index) => (
                <div
                  key={mark.id}
                  ref={(node) => {
                    refs.current.insetBoxes[index] = node
                  }}
                  className={`inset-box ${markClass[mark.kind]}`}
                />
              ))}
            </div>
            <div
              ref={(node) => {
                refs.current.insetShade = node
              }}
              className="absolute inset-0 bg-canvas opacity-0"
            />
            <p className="label-type absolute -top-7 left-0 bg-canvas/70 px-1.5 py-0.5 text-muted">{copy.scene.inset}</p>
          </div>

          <div className="pointer-events-none absolute top-5 right-[clamp(1.25rem,4vw,4.5rem)] z-10 flex flex-wrap justify-end gap-2">
            <p className="label-type border border-line bg-canvas/70 px-2 py-1 text-ink">{copy.scene.mark}</p>
            <p className="label-type border border-tape/60 bg-canvas/70 px-2 py-1 text-tape">{copy.scene.drive}</p>
          </div>

          <div
            ref={(node) => {
              refs.current.curtain = node
            }}
            className="scene-overlay bg-canvas opacity-0"
          />
        </>
    </div>
  )
}

function useVisible(target: React.RefObject<HTMLElement | null>) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const node = target.current
    if (!node) return
    const observer = new IntersectionObserver(([entry]) => setVisible(Boolean(entry?.isIntersecting)))
    observer.observe(node)
    return () => observer.disconnect()
  }, [target])
  return visible
}

export function SiteScene() {
  const pinned = usePinned()
  const reduced = useReduced()
  const wrapper = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({ target: wrapper, offset: ['start start', 'end end'] })
  const mode: ProgressSource['mode'] = reduced ? 'still' : pinned ? 'scroll' : 'loop'
  const source = useRef<ProgressSource>({ mode, scroll: scrollYProgress })
  const visible = useVisible(wrapper)

  useEffect(() => {
    source.current = { mode, scroll: scrollYProgress }
  }, [mode, scrollYProgress])

  const frame: ReactNode = <Frame source={source} active={visible && mode !== 'still'} />

  if (pinned) {
    return (
      <section ref={wrapper} aria-label={copy.scene.title} className="relative" style={{ height: '400vh' }}>
        <div className="sticky top-0 flex h-svh flex-col pt-16">
          <Heading compact />
          <div className="relative min-h-0 flex-1">{frame}</div>
        </div>
      </section>
    )
  }
  return (
    <section ref={wrapper} aria-label={copy.scene.title}>
      <Heading compact={false} />
      <div className="relative h-[min(82svh,46rem)]">{frame}</div>
    </section>
  )
}
