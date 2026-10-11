/** Turning one image embedding and a set of prompt embeddings into a signed margin.
 *
 * Pure, so the arithmetic is unit-tested without downloading a model. The margin is
 * p(positive prompts) − p(negative prompts) under the same softmax a CLIP zero-shot pipeline
 * applies, which keeps the thresholds in `prompts.ts` comparable to the calibration measurements.
 */

export function l2normalize(vector: number[]): number[] {
  const norm = Math.hypot(...vector)
  return norm === 0 ? vector.slice() : vector.map((value) => value / norm)
}

export function dot(a: number[], b: number[]): number {
  if (a.length !== b.length) throw new Error(`cannot compare embeddings of length ${a.length} and ${b.length}`)
  let total = 0
  for (let i = 0; i < a.length; i += 1) total += a[i] * b[i]
  return total
}

/** Numerically stable softmax. */
export function softmax(logits: number[]): number[] {
  const max = Math.max(...logits)
  const exponentials = logits.map((value) => Math.exp(value - max))
  const sum = exponentials.reduce((total, value) => total + value, 0)
  return exponentials.map((value) => value / sum)
}

/** Signed margin in [-1, 1]: positive means the positive prompts won.
 *
 * `cosines` must be ordered positives-first, matching `candidates(spec)`.
 */
export function margin(cosines: number[], positiveCount: number, logitScale: number): number {
  const probabilities = softmax(cosines.map((cosine) => cosine * logitScale))
  const sum = (values: number[]) => values.reduce((total, value) => total + value, 0)
  return sum(probabilities.slice(0, positiveCount)) - sum(probabilities.slice(positiveCount))
}
