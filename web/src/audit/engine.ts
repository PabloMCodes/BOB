import { AutoProcessor, CLIPVisionModelWithProjection, pipeline, RawImage, type ObjectDetectionPipeline } from '@huggingface/transformers'
import { filterPeople, type Person } from './people.ts'
import { candidates, type Spec } from './prompts.ts'
import { dot, l2normalize, margin } from './scoring.ts'
import type { EngineInfo } from './types.ts'

/** The two models the auditor runs, both in the viewer's browser.
 *
 * Their weights and architectures differ from the rover's SH17 YOLOv8 detector.
 * Training-data overlap and independence of errors have not been established.
 *
 * Only the *vision* half of the zero-shot model is downloaded. The prompts are fixed, so their text
 * embeddings ship as a 70 KB file built by `scripts/export-prompt-embeddings.ts`, which drops the
 * first load from the 163 MB a full CLIP pipeline pulls to about 99 MB.
 *
 * Smaller backbones were measured and rejected: MobileCLIP-S0 (12 MB) called clearly helmeted
 * workers bare-headed and "agreed" on vests only by always answering no, and MobileCLIP-S2 (37 MB)
 * still produced helmet disagreements. See `scripts/calibrate-audit.ts`.
 */
export const PERSON_MODEL = 'Xenova/yolos-tiny'
export const ZERO_SHOT_MODEL = 'Xenova/clip-vit-base-patch32'
export const EMBEDDINGS_URL = '/audit/prompt-embeddings.json'

/** Approximate first-load download, measured from the published quantized weights.
 *  yolos-tiny 9.7 MB + clip-vit-base-patch32 vision tower 89.1 MB + prompt embeddings 0.07 MB.
 *  Cached by the browser after the first run. */
export const DOWNLOAD_MB = 99

/** Loading order. WebGPU is far faster where it exists, but a quantized graph can fail to build on
 *  some drivers, so each configuration is tried in turn rather than leaving a visitor with nothing. */
const ATTEMPTS: { device: 'webgpu' | 'wasm'; dtype: 'q8' | 'fp32' }[] = [
  { device: 'webgpu', dtype: 'q8' },
  { device: 'wasm', dtype: 'q8' },
  { device: 'wasm', dtype: 'fp32' },
]

/** Detect generously, then let `filterPeople` apply the measured confidence, size and overlap rules. */
const PERSON_DETECT_THRESHOLD = 0.3

export type Progress = (message: string, fraction: number | null) => void

export type Engine = {
  info: EngineInfo
  people: (image: RawImage) => Promise<Person[]>
  score: (crop: RawImage, spec: Spec) => Promise<number>
}

export type PromptEmbeddings = { model: string; dim: number; logit_scale: number; embeddings: Record<string, number[]> }

function webgpuAvailable(): boolean {
  return typeof navigator !== 'undefined' && 'gpu' in navigator
}

export async function loadEmbeddings(signal?: AbortSignal): Promise<PromptEmbeddings> {
  const response = await fetch(EMBEDDINGS_URL, { signal, cache: 'force-cache' })
  if (!response.ok) throw new Error('The prompt embeddings are missing. Run scripts/export-prompt-embeddings.ts.')
  const data = await response.json() as PromptEmbeddings
  if (data.model !== ZERO_SHOT_MODEL) {
    throw new Error(`The prompt embeddings were built for ${data.model}, but this build uses ${ZERO_SHOT_MODEL}.`)
  }
  return data
}

/** Load both models, reporting download progress. Resolves with the configuration that worked. */
export async function loadEngine(progress: Progress, signal?: AbortSignal): Promise<Engine> {
  const embeddings = await loadEmbeddings(signal)
  const attempts = ATTEMPTS.filter((attempt) => attempt.device !== 'webgpu' || webgpuAvailable())
  let lastError: unknown = null
  for (const attempt of attempts) {
    try {
      progress(`Loading models on ${attempt.device} (${attempt.dtype})…`, null)
      const options = {
        device: attempt.device,
        dtype: attempt.dtype,
        progress_callback: (event: { status?: string; file?: string; progress?: number }) => {
          if (event.status === 'progress' && typeof event.progress === 'number') {
            progress(`Downloading ${event.file ?? 'model'}`, event.progress / 100)
          }
        },
      } as const
      const detector = await pipeline('object-detection', PERSON_MODEL, options) as ObjectDetectionPipeline
      const processor = await AutoProcessor.from_pretrained(ZERO_SHOT_MODEL)
      const vision = await CLIPVisionModelWithProjection.from_pretrained(ZERO_SHOT_MODEL, options)
      progress('Models ready.', 1)
      return engine(detector, processor, vision, embeddings, {
        device: attempt.device, dtype: attempt.dtype, personModel: PERSON_MODEL, zeroShotModel: ZERO_SHOT_MODEL,
      })
    } catch (cause) {
      lastError = cause
      progress(`${attempt.device} (${attempt.dtype}) unavailable, trying another configuration…`, null)
    }
  }
  throw new Error(`No model configuration could run in this browser. ${lastError instanceof Error ? lastError.message : ''}`.trim())
}

type Processor = Awaited<ReturnType<typeof AutoProcessor.from_pretrained>>
type Vision = Awaited<ReturnType<typeof CLIPVisionModelWithProjection.from_pretrained>>

function engine(detector: ObjectDetectionPipeline, processor: Processor, vision: Vision, prompts: PromptEmbeddings, info: EngineInfo): Engine {
  return {
    info,
    async people(image) {
      const found = await detector(image, { threshold: PERSON_DETECT_THRESHOLD }) as unknown as { label: string; score: number; box: { xmin: number; ymin: number; xmax: number; ymax: number } }[]
      const people = found
        .filter((item) => item.label === 'person')
        .map((item) => ({
          score: item.score,
          box: { x: item.box.xmin, y: item.box.ymin, width: item.box.xmax - item.box.xmin, height: item.box.ymax - item.box.ymin },
        }))
      return filterPeople(people, image.height)
    },
    async score(crop, spec) {
      const inputs = await processor(crop)
      const output = await vision(inputs) as { image_embeds: { data: Float32Array | number[] } }
      const embedding = l2normalize(Array.from(output.image_embeds.data))
      const texts = candidates(spec)
      const cosines = texts.map((text) => {
        const vector = prompts.embeddings[text]
        // A reworded prompt without a re-export would otherwise score against nothing at all.
        if (!vector) throw new Error(`No stored embedding for the prompt "${text}". Re-run scripts/export-prompt-embeddings.ts.`)
        return dot(embedding, vector)
      })
      return margin(cosines, spec.positive.length, prompts.logit_scale)
    },
  }
}

export { RawImage }
