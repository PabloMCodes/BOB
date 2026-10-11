/** One inspection pass as a function of progress p in [0, 1]. See web/Motion.md for the table. */

export const ROVER_START_Z = 7.5
export const ROVER_END_Z = 0.8
export const PHONE_HEIGHT = 1.42
export const PHONE_FORWARD = -0.42
export const WHEEL_RADIUS = 0.2

export const SETTLED_P = 0.66
export const LOOP_SECONDS = 20
export const LOOP_END_P = 0.72
export const LOOP_HOLD_SECONDS = 2
export const LOOP_CURTAIN_SECONDS = 0.4
export const LABEL_FADE = 0.025

export type MarkKind = 'hazard' | 'clear' | 'unverified'

export type Mark = {
  id: string
  at: number
  kind: MarkKind
  text: string
  x: number
  z: number
  /** Ground height under the subject (the slab is raised). */
  base: number
  /** Height of the subject's box in the robot's view, from `boxBottom`. */
  boxBottom: number
  boxTop: number
  /** Box width as a fraction of its height on screen. */
  boxRatio: number
}

const HEAD = { boxBottom: 1.22, boxTop: 1.7, boxRatio: 0.9 }
const BODY = { boxBottom: 0, boxTop: 1.74, boxRatio: 0.42 }

/** Subjects are placed so each is inside the phone camera's view when its label appears. */
export const marks: Mark[] = [
  { id: 'eyewear', at: 0.12, kind: 'hazard', text: 'Hazard · PPE · Eyewear', x: -2.3, z: -1.0, base: 0.18, ...HEAD },
  { id: 'helmet', at: 0.2, kind: 'hazard', text: 'Hazard · PPE · Helmet', x: -3.9, z: -2.8, base: 0.18, ...HEAD },
  { id: 'path', at: 0.28, kind: 'hazard', text: 'Hazard · In path', x: 0.1, z: -2.8, base: 0, ...BODY },
  { id: 'zone', at: 0.36, kind: 'hazard', text: 'Hazard · Restricted zone', x: 2.7, z: -0.8, base: 0, ...BODY },
  { id: 'walkway', at: 0.44, kind: 'hazard', text: 'Hazard · Walkway blocked', x: -2.6, z: -4.8, base: 0, boxBottom: 0, boxTop: 1.05, boxRatio: 1.5 },
  { id: 'occluded', at: 0.52, kind: 'unverified', text: 'Unverified · Not assessed', x: 4.0, z: -5.0, base: 0, ...BODY },
  { id: 'clear', at: 0.58, kind: 'clear', text: 'No hazard', x: 1.9, z: -3.6, base: 0, ...BODY },
  { id: 'materials', at: 0.62, kind: 'clear', text: 'No hazard', x: -2.0, z: -6.7, base: 0, boxBottom: 0, boxTop: 1.15, boxRatio: 1.7 },
]

export function clamp01(value: number) {
  return Math.min(Math.max(value, 0), 1)
}

export function smoothstep(edge0: number, edge1: number, value: number) {
  const t = clamp01((value - edge0) / (edge1 - edge0))
  return t * t * (3 - 2 * t)
}

export function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

export function roverZ(p: number) {
  return lerp(ROVER_START_Z, ROVER_END_Z, smoothstep(0.05, 0.7, p))
}

export function labelOpacity(p: number, at: number) {
  return clamp01((p - at) / LABEL_FADE)
}

/** Labels and the inset give way to the top-down Twin view. */
export function detailOpacity(p: number) {
  return 1 - smoothstep(0.74, 0.82, p)
}

export function twinOpacity(p: number) {
  return smoothstep(0.84, 0.92, p)
}

export function twinPathDraw(p: number) {
  return smoothstep(0.85, 0.94, p)
}

type Vec = [number, number, number]
type Key = { pos: Vec; target: Vec }

const ESTABLISH: Key = { pos: [9, 8.5, 14], target: [-0.6, 0, -2] }
const WIDE: Key = { pos: [4.8, 11.5, 9.6], target: [-0.4, 0, -2.6] }
const TOP: Key = { pos: [-0.2, 27, 0.7], target: [-0.2, 0, 0.3] }

function mix(a: Vec, b: Vec, t: number): Vec {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]
}

function fitted(key: Key, fit: number): Key {
  const offset: Vec = [
    (key.pos[0] - key.target[0]) * fit,
    (key.pos[1] - key.target[1]) * fit,
    (key.pos[2] - key.target[2]) * fit,
  ]
  return {
    target: key.target,
    pos: [key.target[0] + offset[0], key.target[1] + offset[1], key.target[2] + offset[2]],
  }
}

/** `fit` pulls the wide shots back on narrow canvases so the pad stays in frame. */
export function cameraAt(p: number, rover: number, fit: number): Key {
  const establish = fitted(ESTABLISH, fit)
  const wide = fitted(WIDE, fit)
  const top = fitted(TOP, Math.max(1, fit * 0.9))
  const shoulder: Key = {
    pos: [1.5 * fit, 2.4 * fit, rover + 3.7 * fit],
    target: [-0.5, 0.8, rover - 6],
  }
  const toShoulder = smoothstep(0.1, 0.4, p)
  const toWide = smoothstep(0.4, 0.66, p)
  const toTop = smoothstep(0.74, 0.9, p)
  const a = { pos: mix(establish.pos, shoulder.pos, toShoulder), target: mix(establish.target, shoulder.target, toShoulder) }
  const b = { pos: mix(a.pos, wide.pos, toWide), target: mix(a.target, wide.target, toWide) }
  return { pos: mix(b.pos, top.pos, toTop), target: mix(b.target, top.target, toTop) }
}
