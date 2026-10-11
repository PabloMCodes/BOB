import type { Rect } from './types.ts'

export type Person = { box: Rect; score: number }

/** How a detected person must look before the auditor will judge it.
 *
 * Measured, not guessed: the first calibration run let a loose detector find five people in a frame
 * containing two, and because one judged subject without PPE makes the whole frame positive, a
 * single spurious box flipped frames to `not_wearing`. Filtering removed a helmet disagreement.
 *
 * This mirrors the vision pipeline's own discipline — it judges only confident, large-enough
 * subjects — rather than inventing a new policy.
 */
export type PersonFilter = { score: number; minHeight: number; nms: number }

export const DEFAULT_FILTER: PersonFilter = { score: 0.85, minHeight: 0.15, nms: 0.55 }

export function iou(a: Rect, b: Rect): number {
  const x1 = Math.max(a.x, b.x)
  const y1 = Math.max(a.y, b.y)
  const x2 = Math.min(a.x + a.width, b.x + b.width)
  const y2 = Math.min(a.y + a.height, b.y + b.height)
  const intersection = Math.max(0, x2 - x1) * Math.max(0, y2 - y1)
  const union = a.width * a.height + b.width * b.height - intersection
  return union <= 0 ? 0 : intersection / union
}

/** Keep confident, large, non-duplicate people, most confident first. Pure, so it is unit-tested. */
export function filterPeople(found: Person[], imageHeight: number, filter: PersonFilter = DEFAULT_FILTER): Person[] {
  const kept: Person[] = []
  for (const person of [...found].sort((a, b) => b.score - a.score)) {
    if (person.score < filter.score) continue
    if (person.box.height < filter.minHeight * imageHeight) continue
    if (kept.some((other) => iou(other.box, person.box) > filter.nms)) continue
    kept.push(person)
  }
  return kept
}
