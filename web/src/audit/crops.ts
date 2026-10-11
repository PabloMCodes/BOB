import type { Spec } from './prompts.ts'
import type { Rect } from './types.ts'

/** How much of a requirement's region the frame actually contains, and where it is.
 *
 * Pure so it can be unit-tested without a model: geometry is the part most likely to be wrong, and
 * a silently misplaced crop would make the auditor answer confidently about the wrong pixels.
 */
export type Crop = { rect: Rect; clipped: number }

/** The region of a person box a requirement is judged on, clamped to the image.
 *
 * Bands may reach outside the person box — a hard hat often pokes above a tight box and boots fall
 * below it — so the requested region can land partly outside the frame. `clipped` is the fraction
 * of the requested area that the image does not contain.
 */
export function cropRect(person: Rect, spec: Spec, imageWidth: number, imageHeight: number): Crop {
  const [top, bottom] = spec.band
  const padX = person.width * spec.pad
  const padY = person.height * spec.pad
  const wanted = {
    x1: person.x - padX,
    y1: person.y + top * person.height - padY,
    x2: person.x + person.width + padX,
    y2: person.y + bottom * person.height + padY,
  }
  const left = Math.max(0, Math.min(Math.floor(wanted.x1), imageWidth - 1))
  const topPx = Math.max(0, Math.min(Math.floor(wanted.y1), imageHeight - 1))
  const right = Math.min(imageWidth, Math.max(Math.ceil(wanted.x2), left + 1))
  const bottomPx = Math.min(imageHeight, Math.max(Math.ceil(wanted.y2), topPx + 1))
  const rect = { x: left, y: topPx, width: right - left, height: bottomPx - topPx }
  const wantedArea = Math.max(1, (wanted.x2 - wanted.x1) * (wanted.y2 - wanted.y1))
  return { rect, clipped: Math.max(0, Math.min(1, 1 - (rect.width * rect.height) / wantedArea)) }
}

/** A crop too small to judge. Mirrors the vision pipeline's refusal to judge tiny subjects. */
export function tooSmall(rect: Rect, spec: Spec): boolean {
  return Math.min(rect.width, rect.height) < spec.minPx
}

/** Most of the region a requirement needs lies outside the frame, so it cannot be judged.
 *
 * This is the per-requirement version of the vision config's `ppe.edge_margin`: a person cut off at
 * the bottom of the frame can still be judged for a hard hat, but not for boots.
 */
export const MAX_CLIPPED = 0.25

export function regionOutsideFrame(crop: Crop): boolean {
  return crop.clipped > MAX_CLIPPED
}
