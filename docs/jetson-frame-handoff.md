# Jetson frames: boundary with the website LLM work

Agreement recorded 2026-10-11: Jetson local inference and capture continue without
internet. An optional online model can consume synchronized frames for deeper
analysis. The teammate owns that online inference feature; this handoff describes
the existing frame delivery interface only. No provider calls, prompts, cloud
credentials or online analysis worker are implemented by the Jetson workstream.

## Existing inputs available to the website/backend

- The local laptop hub exposes authenticated `GET /v1/frames?workspace=rover`.
  Each item includes `cursor`, `delivery`, `hub_rx_wall_ns`, `image_status` and
  `record`; the original local observation is in `record.body`.
- `record.body.event` is the unchanged C2 v2 result, including `event_id`,
  `session_id`, `seq_id`, `jetson_receive_ts_ns`, `image_size`, `model_id`, boxes
  and pose validity. It is bound to the original processed frame.
- `record.body.evidence_sha256` identifies its clean upright JPEG. Once
  `image_status` is `available`, retrieve it from authenticated
  `GET /v1/evidence/{sha256}?workspace=rover`. Original boxes are separate metadata.
- For incremental enumeration use `latest=false&after=<next_after>&limit=100`.
  Metadata can arrive before its JPEG: a consumer must revisit pending images,
  not assume cursor advancement means every image was downloaded. The gallery's
  default `latest=true` is a recent-page view, not an exhaustive processing queue.
- `delivery=backfilled` identifies history received through catch-up. It includes
  history present at first connection; it does not alone prove an internet outage.
  `record.source_mode` distinguishes LIVE, REPLAY and SAMPLE. Capture and receipt
  timestamps have separate clock domains; retain those distinctions.

The hub APIs are local to the laptop. Publishing the website does not make this
private HTTP service internet-accessible. Hosted access/online inference remains
the teammate's integration work. Existing API credentials stay outside Git.

## Keep the workstreams separate

Jetson scope: local models, source-frame association, offline archive, verified
JPEG transfer and receipts, rover control. Website LLM scope: online model choice,
provider integration, processing/retry policy, prompts and display of its analysis.
Any online result should retain its source-frame identity and remain distinguishable
from the original local result. Neither image analysis path grants motor authority.

Already-completed frame-gallery changes touch `web/src/dashboard/Dashboard.tsx`,
`Overview.tsx`, `api.ts`, plus new `Frames.tsx`, `frames.css` and
`web/tests/offline-frames.browser.mjs`. They are isolated in the frame-gallery
commit so a teammate can review overlap without mixing in the rover changes.
The API schema is generated at `schema/app/hub-openapi.json`; avoid hand-editing it.

Pull/fetch before work and before pushing; integrate current main through the
feature branch and PR. Current compatibility checks only cover published changes.
Do not overwrite a teammate's unpushed or conflicting implementation to make a
merge appear clean. [Offline setup](offline-frame-demo.md) describes how the
Jetson, laptop hub and local gallery run together.
