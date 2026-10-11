import { Component, lazy, Suspense, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { teamOrigins, type TeamOrigin } from '../data/inspiration.ts'
import globe from '../data/inspirationGlobe.json'
import { useReduced } from '../hooks/useMediaQuery.ts'
import { EASE } from './motion.ts'

const GlobeScene = lazy(() => import('./OriginsGlobeScene.tsx').then(module => ({ default: module.OriginsGlobeScene })))

function canUseWebGL() {
  try {
    const context = document.createElement('canvas').getContext('webgl2')
    if (!context) return false
    context.getExtension('WEBGL_lose_context')?.loseContext()
    return true
  } catch { return false }
}

class GlobeBoundary extends Component<{ children: ReactNode; fallback: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch() { this.props.onFailure() }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

/** Accessible fallback retains the people-to-route interaction without WebGL. */
function FlatGlobe({ selected }: { selected: TeamOrigin['id'] | null }) {
  const person = teamOrigins.find(origin => origin.id === selected)
  return (
    <svg viewBox="100 30 600 540" className="h-full w-full text-ink" aria-hidden="true">
      <path d={globe.sphere} fill="var(--color-plate)" stroke="var(--color-line)" />
      <path d={globe.graticule} fill="none" stroke="var(--color-line)" strokeWidth="0.6" />
      <g stroke="var(--color-canvas)" strokeWidth="0.5">
        {globe.countries.map(country => <path key={country.name} d={country.path} fill={country.name === person?.country ? 'var(--color-ink)' : 'var(--color-line)'} />)}
      </g>
      {globe.origins.filter(origin => selected === null || origin.id === selected).map(origin => (
        <g key={origin.id} opacity={selected ? 1 : 0.4}>
          <path d={origin.route} fill="none" stroke="currentColor" strokeWidth={selected ? 2 : 1} />
          <circle cx={origin.point[0]} cy={origin.point[1]} r="4" fill="currentColor" />
        </g>
      ))}
      <circle cx={globe.destination[0]} cy={globe.destination[1]} r="5" fill="currentColor" />
    </svg>
  )
}

export function OriginsGlobe() {
  const id = useId()
  const reduced = useReduced()
  const frame = useRef<HTMLDivElement>(null)
  const [supported, setSupported] = useState(canUseWebGL)
  const [visible, setVisible] = useState(false)
  const [paused, setPaused] = useState(false)
  const [turn, setTurn] = useState(0)
  const [hovered, setHovered] = useState<TeamOrigin['id'] | null>(null)
  const [focused, setFocused] = useState<TeamOrigin['id'] | null>(null)
  const [pinned, setPinned] = useState<TeamOrigin['id'] | null>(null)
  const selected = hovered ?? focused ?? pinned
  const person = teamOrigins.find(origin => origin.id === selected)

  useEffect(() => {
    const element = frame.current
    if (!element) return
    let inView = false
    const update = () => setVisible(inView && document.visibilityState === 'visible')
    const observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; update() }, { threshold: 0.1 })
    observer.observe(element)
    document.addEventListener('visibilitychange', update)
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', update) }
  }, [])

  const fallback = <FlatGlobe selected={selected} />
  return (
    <div className="mt-12 grid items-center gap-10 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
      <figure className="min-w-0" aria-labelledby={`${id}-caption`}>
        <motion.div
          ref={frame}
          initial={reduced ? false : { opacity: 0, y: 64, scale: 0.88 }}
          animate={reduced ? { opacity: 1, y: 0, scale: 1 } : undefined}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, amount: 0.15 }}
          transition={{ duration: reduced ? 0 : 1.1, ease: EASE }}
          className="origins-globe-frame relative aspect-square max-h-[36rem] w-full" role="img" aria-label={person ? `${person.name}: ${person.country} highlighted, connected to Florida, USA.` : 'Rotating globe connecting our team’s origins to Florida, USA.'}>
          {supported ? (
            <GlobeBoundary fallback={fallback} onFailure={() => setSupported(false)}>
              <Suspense fallback={fallback}>
                <GlobeScene selected={selected} spinning={!paused && !reduced && selected === null} visible={visible} reduced={reduced} turn={turn} />
              </Suspense>
            </GlobeBoundary>
          ) : fallback}
        </motion.div>
        <figcaption id={`${id}-caption`} className="text-center text-sm leading-relaxed text-muted" aria-live="polite">
          <span className="text-ink">{person ? `${person.firstName} · ${person.country} → Florida, USA` : 'Different origins. Together in Florida, USA.'}</span>
          <span className="mt-2 block text-xs">{supported ? 'Drag to explore. Choose a person to follow their connection.' : 'Choose a person to follow their connection. Static globe shown on this browser.'}</span>
        </figcaption>
        {supported ? (
          <div className="mt-5 flex flex-wrap justify-center gap-3" role="group" aria-label="Globe controls">
            <button type="button" className="globe-control cursor-target" aria-label="Rotate globe left" onClick={() => { setPaused(true); setTurn(value => value - 1) }} data-cursor-label="Rotate">↶</button>
            <button type="button" className="globe-control cursor-target" aria-pressed={paused || reduced} disabled={reduced} onClick={() => setPaused(value => !value)} data-cursor-label="Rotation">{reduced ? 'Motion reduced' : paused ? 'Resume rotation' : 'Pause rotation'}</button>
            <button type="button" className="globe-control cursor-target" aria-label="Rotate globe right" onClick={() => { setPaused(true); setTurn(value => value + 1) }} data-cursor-label="Rotate">↷</button>
          </div>
        ) : null}
      </figure>
      <div>
        <p className="eyebrow mb-5 text-muted">The people behind B.O.B</p>
        <div className="grid gap-3" role="group" aria-label="Follow a teammate’s connection to Florida">
          {teamOrigins.map((origin, index) => (
            <motion.button
              key={origin.id}
              initial={reduced ? false : { opacity: 0, x: 28, y: 16, scale: 0.96 }}
              animate={reduced ? { opacity: 1, x: 0, y: 0, scale: 1 } : undefined}
              whileInView={{ opacity: 1, x: 0, y: 0, scale: 1 }}
              whileFocus={{ opacity: 1, x: 0, y: 0, scale: 1, transition: { duration: 0, delay: 0 } }}
              viewport={{ once: true, amount: 0.15 }}
              transition={{ duration: reduced ? 0 : 0.8, delay: reduced ? 0 : index * 0.12, ease: EASE }}
              type="button" aria-pressed={pinned === origin.id} aria-label={`${origin.name}, ${origin.country} to Florida. Select to keep this connection highlighted.`} onPointerEnter={event => { if (event.pointerType === 'mouse') setHovered(origin.id) }} onPointerLeave={() => setHovered(null)} onFocus={() => setFocused(origin.id)} onBlur={() => setFocused(null)} onClick={() => setPinned(value => value === origin.id ? null : origin.id)} className={`cursor-target flex w-full items-center gap-4 rounded-xl border p-5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink ${selected === origin.id ? 'border-ink bg-plate' : 'border-line hover:border-muted'}`} data-cursor-label={origin.firstName}>
              <span className={`flex size-12 shrink-0 items-center justify-center rounded-full border text-sm ${selected === origin.id ? 'border-ink bg-ink text-canvas' : 'border-line text-muted'}`} aria-hidden="true">{origin.initials}</span>
              <span className="min-w-0 flex-1"><span className="block font-medium text-ink">{origin.name}</span><span className="mt-1 block text-sm text-muted">{origin.country} → Florida</span></span>
              <span aria-hidden="true" className="text-muted">↗</span>
            </motion.button>
          ))}
        </div>
        <p className="mt-5 text-sm leading-relaxed text-muted">Hover over a person, focus their card, or tap to keep their connection in view.</p>
        <button type="button" onClick={() => { setPinned(null); setHovered(null); setFocused(null) }} className="cursor-target mt-5 text-sm text-muted underline decoration-line underline-offset-4 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink" data-cursor-label="Reset">Show all connections</button>
        <p className="mt-8 text-xs leading-relaxed text-muted">Markers represent countries and Florida, rather than individual hometowns.</p>
      </div>
    </div>
  )
}
