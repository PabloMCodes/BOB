import type { Requirement } from './types.ts'

/** Where on a person box to look, as fractions of its height, and what to ask about it.
 *
 * The phrasing is not arbitrary. With bare noun phrases ("a construction worker wearing a hard
 * hat") the helmet check never beat break-even against the rover on the calibration stills; with
 * caption-style "a photo of …" prompts — the shape of text CLIP was trained on — the same model and
 * the same crops reached 6 agreements against 1 disagreement. Re-run
 * `node scripts/calibrate-audit.ts` after changing any wording or margin here.
 */
export type Spec = {
  label: string
  band: [number, number]
  pad: number                 // extra context around the band, as a fraction of the person box
  minPx: number               // a crop smaller than this is not judged, mirroring ppe.min_subject_px
  margin: number              // minimum |p(positive) − p(negative)| to commit to an answer
  positive: string[]
  negative: string[]
  note: string | null         // shown in the UI when the cue is known to be weak
}

export const specs: Record<Requirement, Spec> = {
  helmet: {
    label: 'Hard hat',
    band: [-0.06, 0.26],
    pad: 0.06,
    minPx: 40,
    margin: 0.5,
    positive: [
      'a photo of a worker wearing a hard hat',
      'a photo of a construction helmet on a head',
    ],
    negative: [
      'a photo of a bare human head with no hat',
      'a photo of a person with uncovered hair',
    ],
    note: null,
  },
  vest: {
    label: 'High-visibility vest',
    band: [0.16, 0.6],
    pad: 0.04,
    minPx: 40,
    margin: 0.3,
    positive: [
      'a photo of a bright high-visibility safety vest',
      'a photo of a worker in a reflective orange vest',
    ],
    negative: [
      'a photo of plain dark clothing',
      'a photo of a person in an ordinary shirt',
    ],
    note: null,
  },
  gloves: {
    // Hands have no predictable position inside a person box, so this looks at the whole body and
    // the margin is wide on purpose. Expect mostly abstentions; that is the honest result.
    label: 'Gloves',
    band: [0, 1],
    pad: 0,
    minPx: 64,
    margin: 0.99,
    positive: [
      'a photo of hands wearing work gloves',
      'a photo of gloved hands',
    ],
    negative: [
      'a photo of bare hands',
      'a photo of uncovered skin on hands',
    ],
    note: 'Not reported: at every margin that produced an answer this cue also produced a wrong one, so it is set to abstain always.',
  },
  boots: {
    label: 'Safety boots',
    band: [0.8, 1.06],
    pad: 0.06,
    minPx: 40,
    margin: 0.5,
    positive: [
      'a photo of heavy work boots',
      'a photo of safety boots on feet',
    ],
    negative: [
      'a photo of sneakers',
      'a photo of ordinary casual shoes',
    ],
    note: 'The rover has no boots rule at all, so this is an auditor-only observation.',
  },
}

/** Candidate texts in a stable order: positives first, so scoring can split them by count. */
export function candidates(spec: Spec): string[] {
  return [...spec.positive, ...spec.negative]
}
