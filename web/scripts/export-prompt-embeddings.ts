/** Embed the auditor's fixed prompts once, so the browser never downloads a text encoder.
 *
 *     cd web && node scripts/export-prompt-embeddings.ts
 *
 * The prompts in `src/audit/prompts.ts` never change at runtime, so their text embeddings are static
 * data. Shipping them turns a ~43 MB text tower into a ~70 KB JSON file and leaves the browser
 * loading only the vision tower. Re-run this whenever any prompt wording changes — the panel refuses
 * to score a prompt it has no embedding for rather than silently comparing against the wrong vector.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { AutoTokenizer, CLIPTextModelWithProjection } from '@huggingface/transformers'

import { ZERO_SHOT_MODEL } from '../src/audit/engine.ts'
import { candidates, specs } from '../src/audit/prompts.ts'
import { requirements } from '../src/audit/types.ts'

/** CLIP's text encoder has a fixed 77-token context; dynamic padding breaks its position embeddings. */
const CONTEXT_LENGTH = 77
/** AUDIT_MODEL overrides it only for comparison runs; the panel always uses ZERO_SHOT_MODEL. */
const MODEL = process.env.AUDIT_MODEL ?? ZERO_SHOT_MODEL
/** Standard CLIP temperature: exp(ln(1 / 0.07)) ≈ 100. Not present in this repo's config.json. */
const LOGIT_SCALE = 100

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'public/audit/prompt-embeddings.json')

const prompts = [...new Set(requirements.flatMap((r) => candidates(specs[r])))]
const tokenizer = await AutoTokenizer.from_pretrained(MODEL)
const text = await CLIPTextModelWithProjection.from_pretrained(MODEL, { dtype: 'q8' })
const output = await text(tokenizer(prompts, { padding: 'max_length', max_length: CONTEXT_LENGTH, truncation: true }))

const [count, dim] = output.text_embeds.dims as [number, number]
if (count !== prompts.length) throw new Error(`expected ${prompts.length} embeddings, got ${count}`)

const data = Array.from(output.text_embeds.data as Float32Array)
const embeddings: Record<string, number[]> = {}
for (const [index, prompt] of prompts.entries()) {
  const vector = data.slice(index * dim, (index + 1) * dim)
  const norm = Math.hypot(...vector)
  // Stored already L2-normalised, so the browser only needs a dot product.
  embeddings[prompt] = vector.map((value) => Number((value / norm).toFixed(5)))
}

mkdirSync(dirname(out), { recursive: true })
writeFileSync(out, `${JSON.stringify({ model: MODEL, dim, logit_scale: LOGIT_SCALE, embeddings }, null, 0)}\n`)
console.log(`[prompt-embeddings] ${prompts.length} prompts, dim ${dim} -> ${out}`)
