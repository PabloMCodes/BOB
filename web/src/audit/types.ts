/** Requirements the in-browser auditor is scoped to judge.
 *
 * Eyewear is deliberately absent. From the rover's camera angle safety glasses are a handful of
 * pixels wide and the vision config marks the rule `absence: unverified` for exactly that reason;
 * no browser model on a downscaled frame beats it, so the auditor does not pretend to.
 */
export const requirements = ['helmet', 'vest', 'gloves', 'boots'] as const
export type Requirement = typeof requirements[number]

/** The auditor's own conclusion. It never reports a bare "pass": an abstention stays an abstention. */
export type AuditVerdict = 'wearing' | 'not_wearing' | 'cannot_assess'

/** The rover's recorded claim. `unverified` = no judged subject; `unavailable` = the rule is inactive. */
export type RoverVerdict = 'wearing' | 'not_wearing' | 'unverified' | 'unavailable'

/** How the two claims relate. Deliberately four-way — see `compare`. */
export type Outcome = 'agree' | 'disagree' | 'gap' | 'cannot_assess'

export type Rect = { x: number; y: number; width: number; height: number }

/** One person the auditor found itself, with its own per-requirement conclusions. */
export type AuditedSubject = {
  box: Rect
  score: number
  verdicts: Record<Requirement, { verdict: AuditVerdict; margin: number; reason: string | null }>
}

/** One audited frame: the auditor's subjects plus the per-requirement comparison. */
export type AuditedFrame = {
  src: string
  imageSize: [number, number]
  elapsedMs: number
  subjects: AuditedSubject[]
  results: Record<Requirement, { rover: RoverVerdict; auditor: AuditVerdict; outcome: Outcome }>
}

export type EngineInfo = { device: string; dtype: string; personModel: string; zeroShotModel: string }
