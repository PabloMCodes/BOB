import { useMemo, useRef, type RefObject } from 'react'
import { useFrame } from '@react-three/fiber'
import type { MotionValue } from 'motion/react'
import { Fog, PerspectiveCamera, Vector3, type Group, type Mesh } from 'three'
import { setAttributes, setStyle } from './dom.ts'
import { sightMaterial } from './materials.ts'
import { Rover } from './Rover.tsx'
import {
  LOOP_CURTAIN_SECONDS,
  LOOP_END_P,
  LOOP_HOLD_SECONDS,
  LOOP_SECONDS,
  PHONE_FORWARD,
  PHONE_HEIGHT,
  ROVER_START_Z,
  SETTLED_P,
  WHEEL_RADIUS,
  cameraAt,
  clamp01,
  detailOpacity,
  labelOpacity,
  lerp,
  marks,
  roverZ,
  twinOpacity,
  twinPathDraw,
} from './timeline.ts'

export type ProgressSource = {
  mode: 'scroll' | 'loop' | 'still'
  scroll: MotionValue<number>
}

export type OverlayRefs = {
  labels: Array<HTMLDivElement | null>
  insetFrame: HTMLDivElement | null
  insetShade: HTMLDivElement | null
  insetBoxes: Array<HTMLDivElement | null>
  twin: HTMLDivElement | null
  twinPath: SVGPolylineElement | null
  twinDots: Array<SVGCircleElement | null>
  twinRover: SVGCircleElement | null
  curtain: HTMLDivElement | null
}

const LOOP_CYCLE = LOOP_SECONDS + LOOP_HOLD_SECONDS + LOOP_CURTAIN_SECONDS

type Rect = { left: number; top: number; width: number; height: number }

export function Director({
  source,
  overlay,
}: {
  source: RefObject<ProgressSource>
  overlay: RefObject<OverlayRefs>
}) {
  const body = useRef<Group>(null)
  const wheels = useRef<Array<Group | null>>([])
  const sight = useRef<Mesh>(null)
  const clock = useRef(0)
  const point = useMemo(() => new Vector3(), [])
  const target = useMemo(() => new Vector3(), [])
  const robotEye = useMemo(() => new PerspectiveCamera(50, 4 / 3, 0.1, 80), [])

  useFrame((state, delta) => {
    const { gl, camera, size, scene } = state
    const refs = overlay.current
    const mode = source.current.mode

    let p = SETTLED_P
    let curtain = 0
    if (mode === 'scroll') {
      p = clamp01(source.current.scroll.get())
    } else if (mode === 'loop') {
      clock.current = (clock.current + Math.min(delta, 0.05)) % LOOP_CYCLE
      const t = clock.current
      p = Math.min(t / LOOP_SECONDS, 1) * LOOP_END_P
      if (t < LOOP_CURTAIN_SECONDS) curtain = 1 - t / LOOP_CURTAIN_SECONDS
      if (t > LOOP_SECONDS + LOOP_HOLD_SECONDS) {
        curtain = (t - LOOP_SECONDS - LOOP_HOLD_SECONDS) / LOOP_CURTAIN_SECONDS
      }
    }

    const z = roverZ(p)
    body.current?.position.set(0, 0, z)
    const spin = mode === 'still' ? 0 : -(ROVER_START_Z - z) / WHEEL_RADIUS
    for (const wheel of wheels.current) if (wheel) wheel.rotation.x = spin

    const aspect = size.width / Math.max(size.height, 1)
    const fit = Math.min(Math.max(1.55 / aspect, 1), 2.2)
    const key = cameraAt(p, z, fit)
    camera.position.set(key.pos[0], key.pos[1], key.pos[2])
    target.set(key.target[0], key.target[1], key.target[2])
    camera.lookAt(target)
    camera.updateMatrixWorld()
    if (scene.fog instanceof Fog) {
      const distance = camera.position.distanceTo(target)
      scene.fog.near = distance + 4
      scene.fog.far = distance + 30
    }

    robotEye.position.set(0, PHONE_HEIGHT, z + PHONE_FORWARD)
    robotEye.lookAt(0, PHONE_HEIGHT - 1.1, z + PHONE_FORWARD - 10)
    robotEye.updateMatrixWorld()

    const detail = detailOpacity(p)
    sightMaterial.opacity = 0.07 * detail

    const project = (x: number, y: number, depth: number, eye: PerspectiveCamera | typeof camera, w: number, h: number) => {
      point.set(x, y, depth).project(eye)
      return {
        x: (point.x * 0.5 + 0.5) * w,
        y: (-point.y * 0.5 + 0.5) * h,
        front: point.z > -1 && point.z < 1,
      }
    }

    // Labels are placed in reveal order; a label that would cover an earlier one moves up,
    // and its leader line keeps it attached to its subject.
    const placed: Rect[] = []
    marks.forEach((mark, index) => {
      const node = refs.labels[index]
      if (!node) return
      const at = project(mark.x, mark.base + mark.boxTop + 0.3, mark.z, camera, size.width, size.height)
      const opacity = at.front ? labelOpacity(p, mark.at) * detail : 0
      if (opacity <= 0) {
        setStyle(node, { opacity: '0' })
        return
      }
      const width = node.offsetWidth
      const height = node.offsetHeight
      const left = Math.min(Math.max(at.x - width / 2, 6), size.width - width - 6)
      let bottom = at.y
      for (let attempt = 0; attempt < marks.length; attempt += 1) {
        const hit = placed.find(
          (other) =>
            left < other.left + other.width + 6 &&
            left + width > other.left - 6 &&
            bottom - height < other.top + other.height + 4 &&
            bottom > other.top - 4,
        )
        if (!hit) break
        bottom = hit.top - 4
      }
      placed.push({ left, top: bottom - height, width, height })
      setStyle(node, {
        transform: `translate3d(${left}px, ${bottom - height}px, 0)`,
        opacity: String(opacity),
        '--lead': `${Math.max(at.y - bottom, 0)}px`,
        '--lead-x': `${Math.min(Math.max(at.x - left, 0), width)}px`,
      })
    })

    let inset: Rect | null = null
    const frame = refs.insetFrame
    if (frame) {
      setStyle(frame, { visibility: detail > 0.01 ? 'visible' : 'hidden' })
      setStyle(refs.insetShade, { opacity: String(1 - detail) })
      if (detail > 0.01) {
        const canvasRect = gl.domElement.getBoundingClientRect()
        const rect = frame.getBoundingClientRect()
        inset = {
          left: rect.left - canvasRect.left,
          top: rect.top - canvasRect.top,
          width: rect.width,
          height: rect.height,
        }
        const area = inset
        marks.forEach((mark, index) => {
          const box = refs.insetBoxes[index]
          if (!box) return
          const bottom = project(mark.x, mark.base + mark.boxBottom, mark.z, robotEye, area.width, area.height)
          const top = project(mark.x, mark.base + mark.boxTop, mark.z, robotEye, area.width, area.height)
          const height = bottom.y - top.y
          const width = height * mark.boxRatio
          const left = bottom.x - width / 2
          const onScreen =
            bottom.front && top.front && height > 3 && left + width > 0 && left < area.width
          setStyle(box, {
            transform: `translate3d(${left}px, ${top.y}px, 0)`,
            width: `${width}px`,
            height: `${height}px`,
            opacity: String(onScreen ? labelOpacity(p, mark.at) * detail : 0),
          })
        })
      }
    }

    const twin = twinOpacity(p)
    setStyle(refs.twin, { opacity: String(twin) })
    if (twin > 0.001) {
      const draw = twinPathDraw(p)
      const pathEnd = lerp(ROVER_START_Z, z, draw)
      const start = project(0, 0.02, ROVER_START_Z, camera, size.width, size.height)
      const end = project(0, 0.02, pathEnd, camera, size.width, size.height)
      setAttributes(refs.twinPath, { points: `${start.x},${start.y} ${end.x},${end.y}` })
      marks.forEach((mark, index) => {
        const dot = refs.twinDots[index]
        if (!dot) return
        const observedAt = roverZ(mark.at)
        const at = project(0, 0.02, observedAt, camera, size.width, size.height)
        setAttributes(dot, { cx: at.x, cy: at.y })
        setStyle(dot, { opacity: observedAt >= pathEnd - 0.01 ? '1' : '0' })
      })
      setAttributes(refs.twinRover, { cx: end.x, cy: end.y })
    }

    setStyle(refs.curtain, { opacity: String(curtain) })

    gl.setScissorTest(false)
    gl.setViewport(0, 0, size.width, size.height)
    gl.render(scene, camera)
    if (inset) {
      const y = size.height - inset.top - inset.height
      gl.setViewport(inset.left, y, inset.width, inset.height)
      gl.setScissor(inset.left, y, inset.width, inset.height)
      gl.setScissorTest(true)
      if (sight.current) sight.current.visible = false
      gl.render(scene, robotEye)
      if (sight.current) sight.current.visible = true
      gl.setScissorTest(false)
      gl.setViewport(0, 0, size.width, size.height)
    }
  }, 1)

  return <Rover body={body} wheels={wheels} sight={sight} />
}
