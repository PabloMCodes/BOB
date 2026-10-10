# Step 3d — walkway obstruction inspection (fixed camera)

User-confirmed scope for this product demo: "walkway closed" means **blocked by an obstruction**, so
no clear lane of a configured minimum width connects the walkway's entry edge to its exit edge.
The walkway is an operator-drawn **quadrilateral** on a declared-empty reference image from a fixed
(tripod) phone; L-shaped or other polygon walkways are out of scope. Occupancy evidence is change
against that reference — no new model. People are not obstructions: walkway area they hide is
unknown. Findings are for human review with no movement authority, and say nothing about whether
the rover can travel. The first version is a still-image CLI; per-frame findings only, with
persistence across frames deferred to replay (it needs real `iphone_frame_ts_ns` timestamps).

Moving-camera/rover-path use needs floor registration and is deferred. The capture phone (iPhone
16 Pro) has LiDAR, but the app does not stream depth today; depth (object height above the floor,
true footprint) is a possible later evidence source requiring a Swift change and a C1 schema bump.

## Planned findings (lane check not built yet)

| Finding | Meaning |
| --- | --- |
| `possible_walkway_blocked` | No lane exists even when every unknown area is treated as passable |
| `partially_obstructed` | Occupied area exists, but a lane through observed-clear area remains |
| `clear_lane_observed` | A lane exists through observed-clear area. **Not** "walkway safe" |
| `unverified` | The result depends on unknown area, or the reference check failed |

## Progress

| # | Step | Status |
| --- | --- | --- |
| 0 | Sync, contract and finding meanings documented | ✅ |
| 1 | Walkway definition model (`vision/walkway.py` `WalkwayDefinition`) | ✅ unit-tested |
| 2 | Prototype settings (`configs/walkway.yaml`, `WalkwayConfig`) | ✅ unit-tested |
| 3 | Reference check + change mask (`detect_changes`) | ✅ synthetic-tested |
| 4–9 | People handling, lane check, report/evidence image, CLI, persistence tracker, final docs | Planned |

## Contract (`walkway_version: 1`)

Independent of frozen C2 schema v2 and of the scene v1 records (C8 in [integration.md](../integration.md)).
`WalkwayDefinition` holds the walkway ID, the SHA-256 of the exact reference **file** bytes, image
size, four normalized `(x, y)` vertices (top-left origin, convex, ordered), and `entry_edge` /
`exit_edge` (edge *i* runs from vertex *i* to vertex *i+1*; they must be opposite edges). Three
fixed-`true` declarations record operator setup, not facts inferred from pixels: the reference shows
an empty walkway, the camera is fixed, and the walkway is a floor rectangle (needed later to
straighten it for the lane check). `load_reference` rejects any other file, even a similar picture.

## Reference check and change evidence

`detect_changes(reference, image, definition, config)` first checks, **outside the walkway only**:

1. Same image size, else `image_size_mismatch`.
2. Enough background (`min_background_fraction`), else `insufficient_background_for_camera_check`.
3. Camera translation (ECC on a downscaled copy). Failure to converge, e.g. a textureless scene,
   is `camera_check_failed`; a shift over `max_camera_shift_px` is `camera_moved`.
4. Mean brightness change over `max_brightness_change` is `lighting_changed`.
5. Changed background over `max_background_change_fraction` is `background_changed`.

Any failure returns **no change mask at all**. The image is never warped or relit to fit the
reference. Large camera moves can defeat the shift estimate. The background-change check still
makes them unverified, but the reported shift is then unreliable. Only after a valid check is a
mask computed: blurred LAB distance over `change_threshold`, morphological cleanup, blobs under
`min_change_area_px` removed, inside the walkway shrunk by `edge_margin_px`.

Limitations: shadows, glare and reflections change pixels and will read as occupancy; a tall object
also hides floor behind it in the image, so changed area overstates its footprint (biased toward
false "blocked"); an object matching the floor appearance can be missed. Background people or moving
objects can make a frame `background_changed`. All thresholds in `configs/walkway.yaml` are demo
defaults, not lighting calibration or validated accuracy.

## Acceptance so far

`tests/test_walkway.py`: 39 synthetic tests — definition validation (including rejected L-shape /
pentagon / adjacent edges / false declarations), config file equals code defaults, unchanged and
noisy scenes produce no change, an object inside is detected only inside the walkway, an object
outside and a sub-minimum speck produce none, 1 px shift accepted and measured, 5/7 px shifts
`camera_moved`, 3/10/40 px never yield evidence, lighting/background/textureless/size/too-small
cases unverified, reference bound to the exact file. Synthetic results do not measure real floors,
lighting or obstruction accuracy. Physical tripod acceptance (empty, edge box, full-width boxes,
narrow gap, person, lighting change, bumped camera) is pending; no accuracy target has been set.
