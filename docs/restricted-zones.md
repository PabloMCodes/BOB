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
same decoded image; a separate future live/replay sidecar must correlate to its source C2 event.

## Confirmed physical convention for the next feature

The user selected **yellow caution tape forming a closed outline on the floor; inside is restricted**.
Printed markers are not available. Color alone does not establish a real-world restriction:
the operator must explicitly select this convention for the demonstration. Automatic recognition
of the word CAUTION, floor-plane validation and protective stop behavior are not implied.

## Acceptance

Automated geometry tests cover inside/outside/boundary cases, no feet, ambiguous assignment,
small/low-confidence/cropped evidence, malformed polygons and reference-image mismatch.
Real replay/physical validation must additionally cover shadows, unrelated yellow objects,
black tape lettering, perspective, partial/hidden tape, feet occlusion and moving-camera scenes.
Report misses, false findings and unverified rate separately; no worksite accuracy target has
yet been accepted. Retain positive, negative and ambiguous evaluation clips outside training.
