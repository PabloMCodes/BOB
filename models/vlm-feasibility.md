# Experimental VLM artifacts

No training or fine-tuning was performed. These are external pretrained models
for the local feasibility experiment described in
[the measured report](../docs/vlm-feasibility.md), not production PPE models.
No construction-hazard accuracy metrics are claimed.

## Qwen3-VL-2B-Instruct (tested Q4_K_M)

Source: [Ollama Qwen3-VL 2B Instruct](https://ollama.com/library/qwen3-vl:2b-instruct).
Publisher registry manifest SHA-256:
`ea422f1e73652a95479954d8572d3c8c6022f628ce2d38a1a04aae1b7f2d5300`.
Original combined model blob SHA-256:
`aafed9e48b157ae913cee994e0d9ac927af51e256feafbd923bf2852e8856d00`.
Ollama v0.40.2 subsequently produced local compatibility-converted blobs.
Source blobs were hash-verified before loading. Stored under `models/ollama/`.

## SmolVLM-500M-Instruct (tested Q8_0)

Source: [ggml-org Hugging Face conversion](https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF),
revision `72e986006ef53e37cdd3f6d4241c90b0f01df376`.

| File under `models/vlm/` | Verified SHA-256 |
| --- | --- |
| `SmolVLM-500M-Instruct-Q8_0.gguf` | `9d4612de6a42214499e301494a3ecc2be0abdd9de44e663bda63f1152fad1bf4` |
| `mmproj-SmolVLM-500M-Instruct-Q8_0.gguf` | `d1eb8b6b23979205fdf63703ed10f788131a3f812c7b1f72e0119d5d81295150` |

Also downloaded and verified, but **not benchmarked**: Qwen3-VL-2B Q8_0 and its
projector from ggml-org. Their pinned revision/hashes remain in the gitignored
`runs/vlm-feasibility/models.json`. Do not confuse those artifacts with the tested
Ollama Q4_K_M configuration.

See publisher model cards for training provenance and license terms. These
experiments do not change existing detector classes, config keys, or wire schema.
