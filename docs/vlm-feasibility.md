# Jetson scene-understanding feasibility

Measured locally on the Orin Nano 8GB, JetPack 6.2.1 / CUDA 12.6, in the existing
25W mode during the October 10, 2026 session. This is an exploratory benchmark,
not construction-hazard accuracy validation or an integrated feature.

Priority from the team: missing PPE, then unguarded edges and unstable materials,
then walkway obstructions and trip hazards. Keep the existing PPE pipeline as
the primary detector. Any future VLM path should review occasional fresh frames
asynchronously, retain uncertainty, and never control motion or declare a scene safe.

## Method

Three actual indoor phone frames (3186, 3490, 5120) from the existing recording,
resized to a 640-pixel long edge, were reviewed alone and alongside the unchanged
SH17 PPE pipeline. PPE repeatedly processed eight recorded upright images through
`Pipeline`, targeting 10 Hz without accumulating a queue. The VLM prompt requested
at most two evidenced physical hazards, explicit uncertainty, and under 65 words.
Context was 4096 tokens, output limit 160 tokens, temperature 0, seed 42.

No frames were uploaded to a cloud API. Gemini was not benchmarked because API
credentials were unavailable. The footwear weights were still unpublished, so this
does not establish performance with every planned detector running. These indoor
frames contain no labeled examples of unguarded edges or unstable construction
materials; precision/recall cannot be estimated from them.

## Qwen3-VL-2B

Official Ollama `qwen3-vl:2b-instruct`, Q4_K_M, using the official v0.40.2
ARM64 + JetPack 6 runtime, with cloud disabled and a localhost-only listener.

| Measurement | Result |
| --- | --- |
| First image, including initial model load | 108.75 s (90.82 s reported load) |
| Two warmed images, VLM alone | 5.74 s / 4.75 s |
| First concurrent image, including runtime reload | 41.75 s |
| Two warmed images, with PPE | 7.72 s / 7.34 s |
| PPE baseline p50 / p95, 121 frames | 88.15 / 103.13 ms |
| PPE concurrent p50 / p95, 498 frames | 91.67 / 152.95 ms |
| Minimum system available RAM during concurrent requests | 0.75 GiB |
| Peak system swap usage during concurrent requests | 1.45 GiB |
| PPE boxes and rule verdict parity | 498/498 frames matched baseline |

Concurrent percentiles cover the whole phase, including model loading. This is a
short feasibility sample, not a sustained-load or battery-runtime test. RAM is shared
with the GPU; the reported swap is total system usage, not solely model memory.
Ollama performed an automatic local GGUF compatibility conversion and reloaded
between phases; the first concurrent request is not a warmed latency measurement.

Qwen produced unsupported claims: frame 5120 was described as showing a floor crack
and later a floor/wall gap posing a trip risk, neither established by the image.
It also speculated about electrical shock from tabletop clutter. Adding the word
“unverified” did not make these claims grounded. This model is feasible as an
experimental human-reviewed scene describer, but these results do not justify
automatic hazard decisions or replacing the PPE detector.

## SmolVLM-500M comparison

Hugging Face `ggml-org/SmolVLM-500M-Instruct-GGUF`, Q8_0 weights and projector,
run through the verified Ollama-bundled llama-server with the JetPack CUDA backend
explicitly loaded. The initial CPU fallback trial was interrupted and excluded.
This runner capped image tokens at 512; Qwen used Ollama's 1024 minimum. These are
practical candidate configurations, not a controlled model-only comparison.

| Measurement | Result |
| --- | --- |
| First image, excluding server startup | 1.16 s |
| Two warmed images, VLM alone | 0.53 s / 0.47 s |
| Three images with PPE | 0.80 s / 0.65 s / 0.68 s |
| PPE baseline p50 / p95, 122 frames | 87.80 / 101.02 ms |
| PPE concurrent p50 / p95, only 19 frames | 123.80 / 151.50 ms |
| Minimum system available RAM, whole model run | 3.44 GiB |
| Peak system swap, including pages left from Qwen | 1.03 GiB |
| PPE boxes and rule verdict parity | 19/19 frames matched baseline |

SmolVLM ignored most of the hazard instructions and produced simple captions, such
as “The person in the image is wearing headphones and glasses.” It incorrectly
described a blanket as being on the floor in frame 5120. Its shorter responses
also contribute to faster completion times. It is not a useful hazard-review
replacement on this evidence. The very short concurrent sample is insufficient
for a robust latency percentile or a claim that it interferes less with PPE.

## Decision

Local scene description is possible. Of these two tested configurations, Qwen is
the more promising experimental reviewer because it follows the requested task,
but neither is validated for construction hazards. Keep PPE first; do not enable
continuous Qwen reviews by default with this memory margin. A next evaluation
should use labeled examples and negative controls for each priority hazard,
measure false alarms and missed hazards, and repeat concurrency testing with the
footwear model and live server included. Test a lower image-token budget and
context size before choosing a periodic review interval. Gemini remains an
untested cloud alternative, not a measured winner.

After downloads, approximately 73 GiB of disk remained available. Storage is less
restrictive here than shared RAM and GPU contention. Downloaded weights and
runtime/build artifacts were retained for reuse; the temporary servers were stopped.

## Reproduction and artifacts

Local, gitignored artifacts are under `runs/vlm-feasibility/`:
`ollama_benchmark.py`, `ppe_worker.py`, `check_ppe.py`, `ollama-results.json`,
`ppe-parity.json`, runtime logs, publisher manifests, and `environment.json`.
The smaller-model scripts/results are `smol_benchmark.py` and `smol-results.json`.
Use the existing NVIDIA CUDA `.venv`; do not replace its torch with PyPI wheels.
GPU access is required. Stop other inference workloads before benchmarking.

The downloaded runtime archives and source model blobs were SHA-256 verified
against publisher metadata before use. Original Qwen registry manifest SHA-256:
`ea422f1e73652a95479954d8572d3c8c6022f628ce2d38a1a04aae1b7f2d5300`.
Full individual artifact hashes are in the local manifests. Ollama's converted
blobs are derived runtime artifacts rather than additional downloaded weights.

Production server/configuration and schema were not changed. No model was made
an automatic boot service by this experiment.

Validation after benchmarking: `.venv/bin/python -m pytest -q` completed with
373 passed and 5 skipped in 67.15 seconds (optional export/labeling dependencies
and Apple-only MPS). `git diff --check` passed. Both concurrent PPE comparisons
passed the existing box-matching tolerances and exact per-rule frame verdict checks.
