/** Measure the in-browser auditor against the recorded rover verdicts, outside the browser.
 *
 *     cd web && node scripts/calibrate-audit.ts
 *
 * Runs the same models, crop geometry, prompts and comparison logic the dashboard panel uses, on the
 * same published stills, so the decision margins in `src/audit/prompts.ts` come from measurements
 * rather than guesses. Node runs the ONNX models on CPU; the browser uses WebGPU or WASM, so the
 * timings here are not the browser's.
 *
 * This is a calibration set, not a validation set: ten supplied photographs, no labelled ground
 * truth, and the rover's own verdicts are a second model's opinion rather than the right answer.
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { AutoProcessor, CLIPVisionModelWithProjection, pipeline, RawImage } from '@huggingface/transformers'

import { compare, reduceAudit, reduceRover, tally } from '../src/audit/compare.ts'
import { cropRect, regionOutsideFrame, tooSmall } from '../src/audit/crops.ts'
import { PERSON_MODEL, type PromptEmbeddings } from '../src/audit/engine.ts'
import { filterPeople } from '../src/audit/people.ts'
import { candidates, specs } from '../src/audit/prompts.ts'
import { dot, l2normalize, margin as marginOf } from '../src/audit/scoring.ts'
import { requirements, type AuditVerdict, type Outcome, type Requirement, type RoverVerdict } from '../src/audit/types.ts'

const PERSON_DETECT_THRESHOLD = 0.3
const SWEEP = [0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99]

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (path: string) => JSON.parse(readFileSync(join(root, path), 'utf8'))
const fixture = read('public/media/workers/audit-fixture.json')
const prompts = read('public/audit/prompt-embeddings.json') as PromptEmbeddings
/** Whatever model the shipped embeddings were built for, so the two can never drift apart. */
const ZERO_SHOT_MODEL = prompts.model

const ruleOf: Record<Requirement, string> = { helmet: 'helmet', vest: 'vest', gloves: 'gloves', boots: 'boots' }
const active = (requirement: Requirement) => (fixture.active_rules as string[]).includes(ruleOf[requirement])

type Row = { src: string; requirement: Requirement; person: number; margin: number; note: string | null }

const detector = await pipeline('object-detection', PERSON_MODEL)
const processor = await AutoProcessor.from_pretrained(ZERO_SHOT_MODEL)
const vision = await CLIPVisionModelWithProjection.from_pretrained(ZERO_SHOT_MODEL, { dtype: 'q8' })

const rows: Row[] = []
const personCounts: { src: string; auditor: number; rover: number }[] = []

for (const image of fixture.images) {
  const [width, height] = image.image_size
  const raw = await RawImage.read(join(root, 'public', image.src.replace(/^\//, '')))
  const detected = await detector(raw, { threshold: PERSON_DETECT_THRESHOLD }) as { label: string; score: number; box: { xmin: number; ymin: number; xmax: number; ymax: number } }[]
  const people = filterPeople(detected
    .filter((d) => d.label === 'person')
    .map((d) => ({ score: d.score, box: { x: d.box.xmin, y: d.box.ymin, width: d.box.xmax - d.box.xmin, height: d.box.ymax - d.box.ymin } })), height)

  personCounts.push({
    src: image.src.split('/').pop() as string,
    auditor: people.length,
    rover: (image.boxes as { cls_name: string }[]).filter((b) => b.cls_name === 'person').length,
  })

  for (const [index, person] of people.entries()) {
    for (const requirement of requirements) {
      const spec = specs[requirement]
      const crop = cropRect(person.box, spec, width, height)
      const push = (margin: number, note: string | null) => rows.push({ src: image.src, requirement, person: index, margin, note })
      if (tooSmall(crop.rect, spec)) { push(0, 'too_small'); continue }
      if (regionOutsideFrame(crop)) { push(0, 'outside_frame'); continue }
      const patch = await raw.crop([crop.rect.x, crop.rect.y, crop.rect.x + crop.rect.width, crop.rect.y + crop.rect.height])
      const output = await vision(await processor(patch)) as { image_embeds: { data: Float32Array } }
      const embedding = l2normalize(Array.from(output.image_embeds.data))
      const cosines = candidates(spec).map((text) => dot(embedding, prompts.embeddings[text]))
      push(marginOf(cosines, spec.positive.length, prompts.logit_scale), null)
    }
  }
}

console.log(`\nmodels: ${PERSON_MODEL} + ${ZERO_SHOT_MODEL} (vision tower only)`)
console.log(`fixture: ${fixture.model_id} ${fixture.mode}@${fixture.imgsz}, generated ${fixture.generated_utc}`)

console.log('\n=== person detection: auditor vs rover ===')
for (const count of personCounts) console.log(`  ${count.src.padEnd(42)} auditor ${count.auditor}  rover ${count.rover}`)

console.log('\n=== margin distribution per requirement (judged crops only) ===')
for (const requirement of requirements) {
  const margins = rows.filter((r) => r.requirement === requirement && r.note === null).map((r) => r.margin).sort((a, b) => a - b)
  const skipped = rows.filter((r) => r.requirement === requirement && r.note !== null).length
  if (margins.length === 0) { console.log(`  ${requirement.padEnd(8)} no judged crops (${skipped} skipped)`); continue }
  const at = (f: number) => margins[Math.min(margins.length - 1, Math.floor(f * margins.length))].toFixed(2)
  console.log(`  ${requirement.padEnd(8)} n=${String(margins.length).padEnd(3)} skipped=${String(skipped).padEnd(3)} min ${at(0)}  p25 ${at(0.25)}  median ${at(0.5)}  p75 ${at(0.75)}  max ${margins[margins.length - 1].toFixed(2)}`)
}

/** Outcomes at a given set of margins, reduced per frame exactly as the panel does. */
function outcomes(margins: Record<Requirement, number>): Record<Requirement, Outcome[]> {
  const per = { helmet: [], vest: [], gloves: [], boots: [] } as Record<Requirement, Outcome[]>
  for (const image of fixture.images) {
    for (const requirement of requirements) {
      const mine = rows.filter((r) => r.src === image.src && r.requirement === requirement)
      const verdicts: AuditVerdict[] = mine.map((r) =>
        r.note !== null || Math.abs(r.margin) < margins[requirement] ? 'cannot_assess' : r.margin > 0 ? 'wearing' : 'not_wearing')
      const auditor = verdicts.length === 0 ? 'cannot_assess' : reduceAudit(verdicts)
      const seen = (image.verdicts as { rule: string; verdict: string }[]).filter((v) => v.rule === ruleOf[requirement]).map((v) => v.verdict as RoverVerdict)
      per[requirement].push(compare(reduceRover(seen, active(requirement)), auditor))
    }
  }
  return per
}

const configured = Object.fromEntries(requirements.map((r) => [r, specs[r].margin])) as Record<Requirement, number>
console.log('\n=== outcomes at the configured margins ===')
console.log('  margins:', JSON.stringify(configured))
const per = outcomes(configured)
for (const requirement of requirements) {
  const t = tally(per[requirement])
  console.log(`  ${requirement.padEnd(8)} agree ${t.agree}  disagree ${t.disagree}  gap ${t.gap}  abstain ${t.cannot_assess}`)
}
const all = tally(requirements.flatMap((r) => per[r]))
console.log(`  ${'TOTAL'.padEnd(8)} agree ${all.agree}  disagree ${all.disagree}  gap ${all.gap}  abstain ${all.cannot_assess}`)

console.log('\n=== margin sweep (a=agree d=disagree g=rover did not judge x=abstain) ===')
for (const requirement of requirements) {
  const line = SWEEP.map((m) => {
    const t = tally(outcomes({ ...configured, [requirement]: m })[requirement])
    return `m=${m} a${t.agree}/d${t.disagree}/g${t.gap}/x${t.cannot_assess}`
  })
  console.log(`  ${requirement.padEnd(8)} ${line.join('  ')}`)
}

console.log('\n=== every disagreement at the configured margins ===')
let found = 0
for (const image of fixture.images) {
  for (const requirement of requirements) {
    const mine = rows.filter((r) => r.src === image.src && r.requirement === requirement)
    const verdicts: AuditVerdict[] = mine.map((r) =>
      r.note !== null || Math.abs(r.margin) < configured[requirement] ? 'cannot_assess' : r.margin > 0 ? 'wearing' : 'not_wearing')
    const auditor = verdicts.length === 0 ? 'cannot_assess' : reduceAudit(verdicts)
    const seen = (image.verdicts as { rule: string; verdict: string }[]).filter((v) => v.rule === ruleOf[requirement]).map((v) => v.verdict as RoverVerdict)
    const rover = reduceRover(seen, active(requirement))
    if (compare(rover, auditor) !== 'disagree') continue
    found += 1
    console.log(`  ${image.src.split('/').pop()}  ${requirement}: rover ${rover} vs auditor ${auditor}  margins [${mine.map((r) => r.note ?? r.margin.toFixed(2)).join(', ')}]`)
  }
}
if (found === 0) console.log('  none')
