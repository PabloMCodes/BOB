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

## General site photo selection (2026-10-11)

Local PPE remains active. New `site_photos` edge settings select diverse, adequately
exposed/sharp general views, including frames with no people. The existing full
archive remains enabled; selection does not remove old images or PPE evidence.
Each successfully saved selection adds an atomic v1 `notice` with `code=site_photo`,
`details.selection_version=1`, original `source_event_id`, session/sequence,
`evidence_sha256`, selection reason and quality measurements. The observation and
its original C2 result remain unchanged. No new AI model is loaded.

C10 `/v1/frames?site_only=true` returns selected photos; each frame item gains
nullable `site_photo` selection details. Default frame enumeration is unchanged.
The selected gallery is a polling view, not a processing queue: control notices
and observations can synchronize in either order. Online workers should consume
`site_photo` notices from the existing `/v1/logs` history (page backwards), persist
pending event IDs until their observations/JPEGs arrive, and deduplicate by
(edge_id, store_epoch, source_event_id, analysis model/prompt version). Do not treat
an observation cursor as a watermark for late-arriving selection notices.
Original JPEG hash, source labels and local model results must be retained.

Selection uses a 3-second check interval; 0.75 m movement or 25-degree heading
change permits a new view. Otherwise a changed scene is considered after 30 s.
Similar nearby views are suppressed using a small RGB thumbnail. A timeout never
forces a duplicate. Invalid poses use visual-only comparison; no position is
invented. History is bounded to 128 selected views and resets on session/run
changes, so repeats after resets or long revisits are possible. Thresholds are
provisional and require a physical site walk; there is no semantic object identity,
full-site coverage guarantee, or automatic online hazard analysis in this change.

Restart the vision process to enable selection; restart the updated hub and rebuild
or restart the website to expose **Saved camera frames → Site photos**. Existing
archive history is not retroactively selected. Selection also saves its chosen
JPEGs with `archive.enabled: false`, while PPE evidence keeps its existing policy.
This optional setting reduces frame transfers but disables the all-frame archive;
leave the default on for the existing offline recovery demo.

Validation: 48 targeted Python tests passed (selection, saved-frame recovery, PPE
preservation and hub contracts). The production website build and five Node test
files passed. Headless browser acceptance exercised Site photos → All saved
frames plus offline/reconnect behavior using explicitly SAMPLE images. Eight
existing real phone stills passed the default quality gate; selection checks took
13.7 ms median / 19.4 ms p95 on this Jetson (single short sample, synthetic positions,
not a coverage or sustained performance test). Selection runs on the writer thread
at most once per three source-frame seconds; it loads no extra model.

Full integrated Jetson suite: **711 passed, 5 optional/platform skips** in 209.21 s.
