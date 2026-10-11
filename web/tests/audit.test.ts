import assert from 'node:assert/strict'
import { test } from 'node:test'

import { compare, reduceAudit, reduceRover, tally } from '../src/audit/compare.ts'
import { cropRect, MAX_CLIPPED, regionOutsideFrame, tooSmall } from '../src/audit/crops.ts'
import { filterPeople, iou } from '../src/audit/people.ts'
import { candidates, specs } from '../src/audit/prompts.ts'
import { dot, l2normalize, margin, softmax } from '../src/audit/scoring.ts'
import { requirements } from '../src/audit/types.ts'

test('a disagreement needs both sides to have actually judged the frame', () => {
  assert.equal(compare('wearing', 'wearing'), 'agree')
  assert.equal(compare('not_wearing', 'not_wearing'), 'agree')
  assert.equal(compare('wearing', 'not_wearing'), 'disagree')
  assert.equal(compare('not_wearing', 'wearing'), 'disagree')
  // The rover abstaining is not a claim the auditor can contradict.
  assert.equal(compare('unverified', 'not_wearing'), 'gap')
  assert.equal(compare('unavailable', 'wearing'), 'gap')
  // The auditor abstaining never becomes a verdict about the rover.
  assert.equal(compare('not_wearing', 'cannot_assess'), 'cannot_assess')
  assert.equal(compare('unverified', 'cannot_assess'), 'cannot_assess')
})

test('no judged subject never becomes a pass', () => {
  assert.equal(reduceAudit([]), 'cannot_assess')
  assert.equal(reduceAudit(['cannot_assess', 'cannot_assess']), 'cannot_assess')
  assert.equal(reduceAudit(['cannot_assess', 'wearing']), 'wearing')
  // One subject without the required PPE makes the frame positive.
  assert.equal(reduceAudit(['wearing', 'not_wearing']), 'not_wearing')
  assert.equal(reduceRover([], true), 'unverified')
  assert.equal(reduceRover(['unverified'], true), 'unverified')
  assert.equal(reduceRover(['wearing', 'not_wearing'], true), 'not_wearing')
})

test('an inactive rover rule reports as unavailable, never as compliant', () => {
  assert.equal(reduceRover([], false), 'unavailable')
  // Even if verdicts somehow existed, an inactive rule cannot assert anything.
  assert.equal(reduceRover(['wearing'], false), 'unavailable')
})

test('tally counts every outcome and starts at zero', () => {
  assert.deepEqual(tally([]), { agree: 0, disagree: 0, gap: 0, cannot_assess: 0 })
  assert.deepEqual(tally(['agree', 'agree', 'disagree', 'gap']), { agree: 2, disagree: 1, gap: 1, cannot_assess: 0 })
})

test('crop bands are placed on the right part of the person and clamped to the frame', () => {
  const person = { x: 100, y: 100, width: 200, height: 400 }
  const helmet = cropRect(person, specs.helmet, 1000, 1000)
  const boots = cropRect(person, specs.boots, 1000, 1000)
  // The helmet band sits at the top of the person, the boots band at the bottom; they must not overlap.
  assert.ok(helmet.rect.y < boots.rect.y, 'helmet band must be above the boots band')
  assert.ok(helmet.rect.y + helmet.rect.height <= boots.rect.y, 'bands must not overlap')
  // Nothing may leave the image.
  for (const crop of [helmet, boots]) {
    assert.ok(crop.rect.x >= 0 && crop.rect.y >= 0)
    assert.ok(crop.rect.x + crop.rect.width <= 1000)
    assert.ok(crop.rect.y + crop.rect.height <= 1000)
    assert.ok(crop.rect.width > 0 && crop.rect.height > 0)
  }
  assert.equal(helmet.clipped, 0, 'a person in open frame clips nothing')
})

test('a region outside the frame is reported rather than silently shifted inward', () => {
  // A person cut off at the bottom edge: the boots band is mostly outside the image.
  const person = { x: 10, y: 300, width: 200, height: 400 }
  const boots = cropRect(person, specs.boots, 1000, 700)
  assert.ok(boots.clipped > MAX_CLIPPED, `expected a clipped boots band, got ${boots.clipped}`)
  assert.ok(regionOutsideFrame(boots))
  // The same person's helmet band is fully inside, so it stays judgeable.
  assert.ok(!regionOutsideFrame(cropRect(person, specs.helmet, 1000, 700)))
})

test('crops below the minimum pixel size are not judged', () => {
  const tiny = { x: 0, y: 0, width: 10, height: 20 }
  assert.ok(tooSmall(cropRect(tiny, specs.helmet, 1000, 1000).rect, specs.helmet))
  const big = { x: 100, y: 100, width: 300, height: 600 }
  assert.ok(!tooSmall(cropRect(big, specs.helmet, 1000, 1000).rect, specs.helmet))
})

test('person filtering drops low scores, small boxes and duplicates', () => {
  const tall = { x: 0, y: 0, width: 100, height: 400 }
  const people = [
    { box: tall, score: 0.95 },
    { box: { x: 5, y: 5, width: 100, height: 395 }, score: 0.9 },   // duplicate of the first
    { box: { x: 500, y: 0, width: 100, height: 400 }, score: 0.4 },  // too unconfident
    { box: { x: 700, y: 0, width: 20, height: 40 }, score: 0.99 },   // too small
  ]
  const kept = filterPeople(people, 1000)
  assert.equal(kept.length, 1)
  assert.deepEqual(kept[0].box, tall)
})

test('iou is 1 for identical boxes and 0 for disjoint ones', () => {
  const a = { x: 0, y: 0, width: 10, height: 10 }
  assert.equal(iou(a, a), 1)
  assert.equal(iou(a, { x: 100, y: 100, width: 10, height: 10 }), 0)
})

test('softmax and margin agree with a hand-computed example', () => {
  const probabilities = softmax([0, 0])
  assert.deepEqual(probabilities, [0.5, 0.5])
  // Two positives and two negatives, all equal: the margin must be exactly zero.
  assert.equal(margin([0.1, 0.1, 0.1, 0.1], 2, 100), 0)
  // A strongly positive cosine drives the margin towards +1.
  assert.ok(margin([0.4, 0.4, 0.0, 0.0], 2, 100) > 0.99)
  assert.ok(margin([0.0, 0.0, 0.4, 0.4], 2, 100) < -0.99)
})

test('embedding helpers normalise and refuse mismatched lengths', () => {
  const unit = l2normalize([3, 4])
  assert.equal(Number(Math.hypot(...unit).toFixed(6)), 1)
  assert.equal(dot([1, 0], [1, 0]), 1)
  assert.equal(dot([1, 0], [0, 1]), 0)
  assert.throws(() => dot([1, 0], [1, 0, 0]), /length/)
})

test('every requirement has prompts, a positive/negative split and a usable margin', () => {
  for (const requirement of requirements) {
    const spec = specs[requirement]
    assert.ok(spec.positive.length > 0 && spec.negative.length > 0, `${requirement} needs both sides`)
    assert.equal(candidates(spec).length, spec.positive.length + spec.negative.length)
    assert.ok(spec.margin > 0 && spec.margin <= 1, `${requirement} margin must be in (0, 1]`)
    assert.ok(spec.minPx > 0)
  }
  // Eyewear is deliberately out of scope: the rover's own rule is `absence: unverified`.
  assert.ok(!(requirements as readonly string[]).includes('eyewear'))
})

test('the shipped prompt embeddings cover every prompt the panel will score', async () => {
  const { readFileSync } = await import('node:fs')
  const { dirname, join, resolve } = await import('node:path')
  const { fileURLToPath } = await import('node:url')
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
  const file = JSON.parse(readFileSync(join(root, 'public/audit/prompt-embeddings.json'), 'utf8'))
  const { ZERO_SHOT_MODEL } = await import('../src/audit/engine.ts')
  assert.equal(file.model, ZERO_SHOT_MODEL, 'embeddings must be rebuilt when the model changes')
  for (const requirement of requirements) {
    for (const prompt of candidates(specs[requirement])) {
      const vector = file.embeddings[prompt]
      assert.ok(Array.isArray(vector), `no embedding for "${prompt}" — re-run scripts/export-prompt-embeddings.ts`)
      assert.equal(vector.length, file.dim)
      assert.equal(Number(Math.hypot(...vector).toFixed(3)), 1, 'stored embeddings must be L2-normalised')
    }
  }
})
