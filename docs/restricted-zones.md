# Step 3c — restricted-zone inspection

Implementation proceeds in separate feature commits: (1) image-bound operator zone,
(2) yellow caution-tape boundary recognition, (3) Mac live/replay integration.
Walkway obstruction, edges/stairs, crossing events and world-map registration remain deferred.
No actuator, navigation or safety-supervisor behavior is introduced.

## Feature 1: an operator-defined zone on an upright still image

```bash
uv run python -m tools.inspect_zone path/to/upright.jpg \
  --polygon '0.1,0.6;0.8,0.6;0.8,0.95;0.1,0.95' --out runs/zones/my-inspection
```

Supply ordered, normalized x/y vertices around a convex boundary. The origin is the image's
top-left. The image must already be upright; the tool does not interpret EXIF or ARKit rotation.
The output directory must be new. It contains `zone.json`, `findings.json`, and `annotated.jpg`.
`--zone runs/zones/my-inspection/zone.json` reuses a definition on its exact reference image.
A different image hash or dimensions invalidates it, even if the picture looks similar.
This deliberately does not treat a static pixel polygon as a moving-camera registration.

The existing shared `Pipeline` runs once. Person boxes identify subjects; separate model boxes
for visible foot/footwear supply approximate contact points at their bottom centers. Person-box
overlap or its bottom edge alone is never sufficient. Generic SH17 shoes may provide geometry
evidence here; they are not used to infer safety-boot compliance.

Findings:

- `possible_person_in_zone`: a confident visible-foot contact proxy lies clearly inside.
- `observed_feet_outside`: the available foot proxies lie outside; this is not person clearance.
- `unverified`: insufficient person/foot evidence, ambiguous ownership between people,
  cropped/tiny feet, proximity to the boundary, or invalid zone registration.

A zone with no detected people has no person assessments, not an all-clear result. Model errors,
occlusion and raised feet can invalidate the contact-point assumption; these are inspection
candidates for human review, not verified ground positions. Default confidence (0.50), foot
size (12 px), and boundary margin (6 px) are prototype evidence filters, not validated worksite
accuracy thresholds. No metric distance or hazard world location is inferred.

## Scene contract

The independent scene output uses `scene_version: 1`. Existing C1/C2/C3 schema v2 is unchanged.
An image definition contains zone identity, image hash, dimensions and normalized polygon.
The still-image report contains observation identity, source mode `STILL`, source image hash,
model identity/class mapping, image dimensions, original boxes and a scene assessment.
Person/evidence indices refer to that report's original boxes. Evidence and assessment use the
same decoded image. Live/replay sidecars correlate to the exact source C2 event as described below.

## Feature 2: closed yellow caution-tape recognition

The user selected **yellow caution tape forming a closed outline on the floor; inside is restricted**.
Printed markers are not available. Color alone does not establish a real-world restriction:
the operator must explicitly select this convention for the demonstration. Automatic recognition
of the word CAUTION, floor-plane validation and protective stop behavior are not implied.

```bash
uv run python -m tools.inspect_zone path/to/upright.jpg \
  --tape-config configs/zones-yellow.yaml --out runs/zones/tape-inspection
```

The opt-in profile explicitly declares that the visible yellow outline is on the floor and its
inside is restricted. The detector uses a complete enclosed region in the current yellow mask.
It does not infer a boundary from a yellow blob, connect separated strips, or reuse an old
outline. Multiple plausible regions, an incomplete loop, a cropped outer boundary or strongly
nonconvex geometry produce `unverified`. The polygon follows the tape's inner edge, so proximity
to the tape remains uncertain. A fully visible convex outline is a deliberate first-version limit.

The HSV thresholds in `configs/zones-yellow.yaml` are demo defaults, not lighting calibration.
Small lettering is tolerated only while the yellow outline remains connected. Wide black print,
occlusion, shadows or glare may break the loop and therefore prevent assessment. A yellow closed
object unrelated to tape can still fool this color/shape method; the operator convention and
controlled setup are necessary. Actual floor tape footage and physical acceptance are pending.
The separate image-bound polygon mode remains available and unchanged.

One real photograph of yellow floor tape has now been run through `tools.inspect_zone`
(a 5S door-range line on a tiled floor, kept with the website assets in
`runs/showcase/web-zones/`). It returns `unverified / no_complete_yellow_outline`, which is the
correct answer: the tape is found as yellow, covering 2.9% of the image, but the boundary is
closed by the walls rather than by tape, so the largest enclosed region is 44 px of speckle
against the 1% minimum. This is one still of an indoor floor line, not worksite footage: it
shows the refusal path behaving as specified and says nothing about recognition accuracy.
No photograph tested so far produces a `recognized` zone, so physical acceptance is unchanged.

## Feature 3: Mac live/replay inspection

Run the live server with the opt-in tape profile:

```bash
uv run python -m vision.server --detect --zones configs/zones-yellow.yaml --record
```

The existing PPE view remains separate from the **BOB restricted zones** window. The latter
shows the current image-local boundary, foot evidence and uncertainty. It marks an old
observation stale using its frame receive time, even if pose packets continue arriving, and
clears the displayed boundary when the source session changes. Each frame is assessed anew;
moving the phone does not reuse a static image polygon or establish map registration.

Replay a recording with separate zone evidence images:

```bash
uv run python -m tools.replay_detect path/to/stream.bobrec \
  --zones configs/zones-yellow.yaml --save-images --out runs/zones/my-replay
```

Both paths reuse the existing admitted frame and shared detection result; scene inspection
does not run another model. Add `--config configs/footwear.yaml` to either command to use the
existing opt-in footwear specialist. Network-fed sample/replay streams must be labeled using
the server's `--zones-source-mode SAMPLE` or `REPLAY`; normal phone input defaults to `LIVE`.
Offline outputs are labeled `REPLAY`; synthetic footage must also be visibly identified as sample data.

Outputs in the run directory:

- `scene_findings.jsonl`: one attempted observation per processed frame, keyed by
  `source_event_id` into `detections.jsonl`, with session, sequence and iPhone capture timestamp.
  Person/evidence indices refer to that C2 event's boxes.
- `zone_profile.json`: effective operator declarations and thresholds. Each observation records
  the profile hash and the SHA-256 of the upright decoded BGR pixel bytes.
- `zone_frames/<source_event_id>.jpg`: separately annotated replay evidence when `--save-images`
  is enabled. Live `--record` preserves the source recording for later replay.

Valid associated pose means **camera observation position**, never the person's or zone's world
position. Invalid pose leaves the image-local observation unlocalized. A retired-session event
has an unverified boundary. Frozen C2 schema v2 and existing PPE verdicts are unchanged.

Live scene output uses a bounded queue of eight records and drops new records on overflow.
Console counters and `summary.json` report written/dropped records, storage errors and pending
work; shutdown waits at most two seconds. This is an observation log, not durable incident
storage. Only this scene sink is asynchronous; existing C2/recording storage is unchanged.
Offline replay writes synchronously. `scene_processing_ms` measures boundary/assessment/hash
work; server processing latency includes scene analysis/submission but excludes asynchronous
scene disk writes and the separate zone window. No new live latency claim is made here.

## Acceptance

Mac verification: **339 full-suite tests pass**, including 35 zone/tape/scene tests and server
CLI integration with scene output enabled/disabled. Six synthetic JPEG frames through the real
SH17 replay pipeline produced three recognized complete outlines and three unverified broken
or absent outlines; all six sidecars matched their C2 event IDs. Portrait/landscape handling,
session changes, missing foot evidence, queue overflow and storage failure have automated checks.
Synthetic results do not measure physical tape or person-in-zone accuracy.

Automated geometry tests cover inside/outside/boundary cases, no feet, ambiguous assignment,
small/low-confidence/cropped evidence, malformed polygons and reference-image mismatch.
Real replay/physical validation must additionally cover shadows, unrelated yellow objects,
black tape lettering, perspective, partial/hidden tape, feet occlusion and moving-camera scenes.
Report misses, false findings and unverified rate separately; no worksite accuracy target has
yet been accepted. Retain positive, negative and ambiguous evaluation clips outside training.
