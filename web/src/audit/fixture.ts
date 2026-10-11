import { reduceRover } from './compare.ts'
import { requirements, type Requirement, type RoverVerdict } from './types.ts'

/** The recorded output of the real `vision.pipeline` on the published stills, written by
 *  `uv run python -m tools.export_audit_fixture`.
 *
 *  This is what the auditor compares itself against when there is no hub — on the deployed site, or
 *  on any visitor's machine. It is evidence of what the rover's model claimed, never ground truth.
 */
export type FixtureBox = { source: string; cls_name: string; conf: number; xyxy: number[] }
export type FixtureVerdict = { rule: string; verdict: string; subject: FixtureBox; ppe: FixtureBox | null; violation: FixtureBox | null }
export type FixtureImage = { src: string; image_size: [number, number]; inference_ms: number; passes: number; boxes: FixtureBox[]; verdicts: FixtureVerdict[] }
export type Fixture = {
  fixture_version: number
  generated_utc: string
  note: string
  model_id: string
  weights_sha256: string | null
  device: string
  mode: string
  imgsz: number
  active_rules: string[]
  inactive_rules: { name: string; missing_classes: string[] }[]
  images: FixtureImage[]
}

export const FIXTURE_URL = '/media/workers/audit-fixture.json'
const SUPPORTED_VERSION = 1

/** Requirement names as the browser uses them → the vision config's rule names. Kept explicit so a
 *  renamed rule surfaces as a missing rule rather than silently reading as "not required". */
const ruleOf: Record<Requirement, string> = { helmet: 'helmet', vest: 'vest', gloves: 'gloves', boots: 'boots' }

export async function loadFixture(signal?: AbortSignal): Promise<Fixture> {
  const response = await fetch(FIXTURE_URL, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('The recorded rover verdicts are unavailable. Re-run tools.export_audit_fixture.')
  const data = await response.json() as Fixture
  if (data.fixture_version !== SUPPORTED_VERSION) {
    throw new Error(`This build reads audit fixture v${SUPPORTED_VERSION}, but the file is v${data.fixture_version}.`)
  }
  if (!Array.isArray(data.images) || data.images.length === 0) throw new Error('The audit fixture contains no frames.')
  return data
}

/** A rule is active only if the pipeline that produced the fixture had every class it needs.
 *  An inactive rule is a missing capability, never a pass. */
export function ruleActive(fixture: Fixture, requirement: Requirement): boolean {
  return fixture.active_rules.includes(ruleOf[requirement])
}

export function missingClasses(fixture: Fixture, requirement: Requirement): string[] {
  return fixture.inactive_rules.find((r) => r.name === ruleOf[requirement])?.missing_classes ?? []
}

/** The rover's claim about one frame, per requirement. */
export function roverClaims(fixture: Fixture, image: FixtureImage): Record<Requirement, RoverVerdict> {
  const claims = {} as Record<Requirement, RoverVerdict>
  for (const requirement of requirements) {
    const rule = ruleOf[requirement]
    const seen = image.verdicts.filter((v) => v.rule === rule).map((v) => v.verdict as RoverVerdict)
    claims[requirement] = reduceRover(seen, ruleActive(fixture, requirement))
  }
  return claims
}
