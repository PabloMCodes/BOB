import { compare, reduceAudit } from './compare.ts'
import { cropRect, regionOutsideFrame, tooSmall } from './crops.ts'
import { RawImage, type Engine } from './engine.ts'
import { roverClaims, type Fixture, type FixtureImage } from './fixture.ts'
import { specs } from './prompts.ts'
import { requirements, type AuditVerdict, type AuditedFrame, type AuditedSubject, type Requirement } from './types.ts'

const NO_PERSON = 'The auditor found no person in this frame.'

/** Audit one frame: find people with the auditor's own detector, judge each requirement on its own
 *  crop, then relate the result to what the rover claimed.
 *
 *  Every abstention carries a reason. "No violation found" is never reported as compliance.
 */
export async function auditFrame(engine: Engine, fixture: Fixture, image: FixtureImage): Promise<AuditedFrame> {
  const started = performance.now()
  const [width, height] = image.image_size
  const raw = await RawImage.fromURL(new URL(image.src, window.location.origin))
  const people = await engine.people(raw)
  const subjects: AuditedSubject[] = []

  for (const person of people) {
    const verdicts = {} as AuditedSubject['verdicts']
    for (const requirement of requirements) {
      const spec = specs[requirement]
      const crop = cropRect(person.box, spec, width, height)
      if (tooSmall(crop.rect, spec)) {
        verdicts[requirement] = { verdict: 'cannot_assess', margin: 0, reason: `Region is smaller than ${spec.minPx} px.` }
        continue
      }
      if (regionOutsideFrame(crop)) {
        verdicts[requirement] = { verdict: 'cannot_assess', margin: 0, reason: 'The region needed is mostly outside the frame.' }
        continue
      }
      const patch = await raw.crop([crop.rect.x, crop.rect.y, crop.rect.x + crop.rect.width, crop.rect.y + crop.rect.height])
      const margin = await engine.score(patch as RawImage, spec)
      const verdict: AuditVerdict = Math.abs(margin) < spec.margin ? 'cannot_assess' : margin > 0 ? 'wearing' : 'not_wearing'
      verdicts[requirement] = {
        verdict,
        margin,
        reason: verdict === 'cannot_assess' ? `Inconclusive: margin ${margin.toFixed(2)} is under ${spec.margin}.` : null,
      }
    }
    subjects.push({ box: person.box, score: person.score, verdicts })
  }

  const rover = roverClaims(fixture, image)
  const results = {} as AuditedFrame['results']
  for (const requirement of requirements) {
    const auditor = subjects.length === 0 ? 'cannot_assess' : reduceAudit(subjects.map((s) => s.verdicts[requirement].verdict))
    results[requirement] = { rover: rover[requirement], auditor, outcome: compare(rover[requirement], auditor) }
  }

  return { src: image.src, imageSize: [width, height], elapsedMs: performance.now() - started, subjects, results }
}

/** Why a frame produced nothing, in words the panel can show verbatim. */
export function frameNote(frame: AuditedFrame): string | null {
  if (frame.subjects.length > 0) return null
  return NO_PERSON
}

/** Audit every frame in order, reporting each as it finishes so the panel fills progressively. */
export async function auditAll(
  engine: Engine,
  fixture: Fixture,
  onFrame: (frame: AuditedFrame, index: number) => void,
  shouldStop: () => boolean,
): Promise<void> {
  for (const [index, image] of fixture.images.entries()) {
    if (shouldStop()) return
    onFrame(await auditFrame(engine, fixture, image), index)
  }
}

export type { Requirement }
