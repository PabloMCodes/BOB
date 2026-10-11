import type { AuditVerdict, Outcome, RoverVerdict } from './types.ts'

/** Relate the auditor's conclusion to the rover's recorded claim.
 *
 * Four outcomes, not two. A plain agree/disagree counter would be misleading here: the rover
 * reports `unverified` whenever no subject was judged and `unavailable` whenever the rule is
 * inactive, and neither is a claim the auditor can contradict.
 *
 *   agree         both judged the frame and reached the same answer
 *   disagree      both judged it and reached different answers — one of them is wrong
 *   gap           the rover did not judge it; the auditor has an opinion, unconfirmed
 *   cannot_assess the auditor abstained
 *
 * A disagreement is not evidence that the rover is wrong. Two models differing establishes that one
 * of them is, not which, and nothing here is ground truth.
 */
export function compare(rover: RoverVerdict, auditor: AuditVerdict): Outcome {
  if (auditor === 'cannot_assess') return 'cannot_assess'
  if (rover === 'unverified' || rover === 'unavailable') return 'gap'
  return rover === auditor ? 'agree' : 'disagree'
}

/** Reduce per-subject conclusions to one claim about the frame.
 *
 * Frame-level is the granularity the project already uses for incidents: the confirmation policy
 * tracks a condition per (inspection, session, rule) — "someone in view is missing required
 * eyewear" — rather than a violation by an identified worker. The auditor finds its own people, so
 * its subjects do not line up one-to-one with the rover's anyway.
 *
 * `not_wearing` dominates: one judged subject without the required PPE makes the frame positive.
 * Absence of a positive is never promoted to a pass — with no judged subject the frame abstains.
 */
export function reduceAudit(verdicts: AuditVerdict[]): AuditVerdict {
  if (verdicts.includes('not_wearing')) return 'not_wearing'
  if (verdicts.includes('wearing')) return 'wearing'
  return 'cannot_assess'
}

export function reduceRover(verdicts: RoverVerdict[], ruleActive: boolean): RoverVerdict {
  if (!ruleActive) return 'unavailable'
  if (verdicts.includes('not_wearing')) return 'not_wearing'
  if (verdicts.includes('wearing')) return 'wearing'
  return 'unverified'
}

export const outcomeLabels: Record<Outcome, string> = {
  agree: 'Agree',
  disagree: 'Disagree',
  gap: 'Rover did not judge',
  cannot_assess: 'Auditor abstained',
}

/** Running totals across audited frames. */
export type Tally = Record<Outcome, number>

export function tally(outcomes: Outcome[]): Tally {
  const counts: Tally = { agree: 0, disagree: 0, gap: 0, cannot_assess: 0 }
  for (const outcome of outcomes) counts[outcome] += 1
  return counts
}
