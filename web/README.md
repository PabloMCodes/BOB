# BOB product page

Local Vite app for the product page and the operator dashboard at `/dashboard`. The dashboard connects to the laptop hub for measured FPS/Hz/confidence, preview, connections, backend logs, detections, incidents, evidence and a session-specific digital twin. Site managers can save the five PPE requirements and explicitly start/end an inspection using a saved revision. SAMPLE is a separate read-only workspace.

See [the digital twin integration guide](../docs/plans/digital-twin-frontend-guide.md) for startup, authentication, data semantics and verification. The default hub is `http://127.0.0.1:8780`; connection settings allow a different address. An optional `VITE_HUB_URL` sets the initial address, never a token.

Fixed choices use `src/components/Select.tsx`: workspace, saved worksite, each PPE requirement, session and log event type. PPE selections are **Required** / **Not required** and save the existing backend booleans. Worksite options come from the hub; **Create a worksite** opens the name/ID fields for a new entry. The native selects retain keyboard and mobile picker behavior.

**Export visible detections (CSV)** downloads the latest displayed frames for the selected session/workspace. It includes worksite/inspection revision, source mode, delivery, frame/model, measured inference time, each box's confidence percentage and confidence basis, and all five frame-level PPE statuses/reasons exactly as recorded. There is one row per box, with an empty-box row for frames without detections; repeated frame assessments are not individual-worker verdicts. Missing assessments stay blank with `assessment_recorded=false`, never an inferred pass. Export/refreshed timestamps and a stale flag identify the snapshot. Only allowlisted metadata is included: no images, evidence references, hub address or browser credentials. CSV quoting preserves multiline text and neutralizes formula-like text in spreadsheet apps. Downloaded files remain subject to the operator-managed privacy policy.

## Second opinion (in-browser audit)

The dashboard's **Second opinion** panel re-judges recorded frames with models with different weights
and architectures from the rover's SH17 detector, entirely in the viewer's browser:
`Xenova/yolos-tiny` finds people and the `Xenova/clip-vit-base-patch32` vision tower judges each
requirement on its own crop of the person box. Nothing is uploaded and no hub is required, so the
panel also works on the deployed site. Results live in memory only — they are not evidence, are not
stored, and do not reach the hub.

It compares against `public/media/workers/audit-fixture.json`, the real `vision.pipeline` output for
the published stills, regenerated with `uv run python -m tools.export_audit_fixture` from the
repository root. Outcomes are four-way: **agree**, **disagree**, **rover did not judge** (the rover
abstained or the rule is inactive) and **auditor abstained**. Training-data overlap has not been verified. A disagreement prompts human review; it does not
establish which claim is correct.

Only the *vision* half of the zero-shot model is downloaded. The prompts are fixed, so their text
embeddings are precomputed into `public/audit/prompt-embeddings.json` by
`node scripts/export-prompt-embeddings.ts`; re-run it after changing any prompt wording, or the panel
will refuse to score the changed prompt. First load is roughly 99 MB (9.7 MB detector + 89.1 MB
vision tower), cached by the browser afterwards. WebGPU is used when available, with a WASM fallback.

`node scripts/calibrate-audit.ts` measures the auditor against the fixture and prints the margin
distribution, a margin sweep and every disagreement. The decision margins in `src/audit/prompts.ts`
were chosen from it — re-run it after changing prompts, crop bands or models. Measured on the ten
published stills: **13 agree, 0 disagree, 9 rover-did-not-judge, 18 auditor-abstained** across 40
frame-requirement comparisons, with helmet agreeing on 10 of 10 frames. Those prompts and margins
were tuned on these same ten frames, so this is calibration-set behaviour, not validation: the set
has no labelled ground truth, and nothing here establishes worksite accuracy.

Scope is helmet, vest, gloves and boots. Eyewear is excluded because safety glasses are a few pixels
wide at the rover's camera distance and the vision config marks that rule `absence: unverified` for
the same reason. Gloves is set to abstain always: at every margin that produced an answer it also
produced a wrong one, because hands have no predictable position inside a person box. The rover has
no boots rule at all (its model lacks a `safety-boots` class), so boots is auditor-only and can never
agree or disagree. Smaller backbones were measured and rejected — MobileCLIP-S0 (12 MB) called
clearly helmeted workers bare-headed, and MobileCLIP-S2 (37 MB) still produced helmet disagreements.

Read [Design.md](Design.md) before changing layout or color. Read [Motion.md](Motion.md) before changing scroll, the detection boxes, or the closing scene.

The worker privacy and safety policy is at `/privacy`, linked from the homepage footer and dashboard. Its copy lives in `src/data/privacy.ts`. Routine images have a maximum retention of 7 days from capture; incident evidence has 30 days, with narrowly documented holds. These are operator-managed policy limits: expiry of hub replicas, saved previews, recordings, exports and backups is not implemented. Rover pruning alone does not enforce this policy across all copies. The site operator must provide a privacy contact, arrange deletion and verify the schedule before capturing workers.

Terms of Service are at `/terms`, linked from the homepage, dashboard and privacy page. Copy and the supplied operator/contact details live in `src/data/terms.ts`. Terms cover authorized prototype use, human review, worker data, availability, warranty limitations and separate component licenses. Retention periods are read from the privacy policy so both pages agree. The terms do not change the original-code MIT license or third-party permissions.

```bash
npm install
npm run dev
```

`npm run build` typechecks and writes `dist/`. `npm run lint` runs oxlint. Run the dashboard client checks with `node --test tests/twin.test.ts tests/twin-map.test.mjs tests/dashboard.test.ts tests/detection-csv.test.ts tests/audit.test.ts` (Node with native TypeScript support).

The Vite development server proxies the configured default hub through `/_bob/hub`, including Authorization headers, so development previews on any local port can connect without changing the hub's CORS settings. A different address entered in Connection settings is accessed directly and must allow the browser origin. Production builds (`vite preview` included) must configure CORS or their own authenticated reverse proxy; the development proxy is not part of `dist/`.

## Filling in the homepage

The **Inspiration** navigation tab opens `/inspiration`: six build-story chapters lead to a rotating, draggable globe near the end of the page. Hovering or focusing a teammate card lights only that person's country and connection to Florida; clicking or tapping pins the connection, and **Show all connections** resets it. Confirmed origins: Humberto Bohorquez → Venezuela, Pablo Mendoza → Mexico, Maham Mehmood → Pakistan. Country markers are approximate, not personal hometown locations. Pause/resume and manual rotation controls support keyboard use; automatic rotation stops during selection, offscreen, in background tabs and under reduced motion.

The first three narratives and five of ten photo boxes are intentionally empty. Edit `src/data/inspiration.ts` to add stories or replace a `src: null` photo with a path under `public/media/`; give each real photo descriptive `alt` text. Existing robot photos illustrate the workbench, printed parts, onboard computer and current chassis. They do not establish completed Jetson deployment or field acceptance.

Framer Motion (`motion/react`) adds a reading-progress line, chapter and photo reveals, subtle scroll-linked photo movement, and a globe/team entrance. Scrolling remains native on this page. Reduced-motion preferences show the settled layout with all scroll effects disabled; animation values are documented in `Motion.md`.

The page emphasizes working together with a masked word reveal and a team signature whose three paths join into B.O.B. The build, connection and rover chapters include `teamwork` entries for the failed print and four-hour restart, Jetson power conversion, and ESP32 wheel/encoder integration. Challenges came from team notes; the suggested responses are visibly marked **Draft team notes**. After verifying a response, edit its text and change `responseStatus` to `confirmed` in `src/data/inspiration.ts`.

The globe uses the existing Three.js/React Three Fiber stack and OrbitControls, with local textures under `public/media/globe/`; no remote tiles or new dependencies. Textures and the static SVG fallback in `src/data/inspirationGlobe.json` derive from [Natural Earth 110m country outlines](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson) (public domain), projected with d3-geo. If WebGL or texture loading fails, the static fallback retains teammate selection and highlights. Great-circle arcs connect each country to Florida; selecting a teammate frames both endpoints.

The section plan is [docs/plans/homepage-redesign-plan.md](../docs/plans/homepage-redesign-plan.md).

| What | Where |
| --- | --- |
| Headline, paragraphs, card text, team, GitHub link, YouTube ID | `src/data/copy.ts` |
| Hero background (photo or clip) | file in `public/media/hero/`, entry `heroBackground` in `src/data/media.ts` |
| Skill card photos or clips | files in `public/media/skills/`, entries in `skillMedia` keyed by the card `id` |

A card without media shows a dark plate with its number. If a photo's boxes are already drawn into the file, leave `boxes` out. For a clean photo, list `boxes` as fractions of the original image (`x`, `y`, `w`, `h`, `label`), measured from the file.

The `eyewear` and `zones` cards use Creative Commons stock photographs, not rover captures, with boxes drawn by the real pipeline. `public/media/skills/sources.json` records each photograph's author, licence and Commons page, and what the detector actually returned — including the zone card, which shows an honest `unverified` result because no photograph tested so far contains a tape loop closed by tape. Both photographs are share-alike, so the annotated versions carry the same licence; the footer credits them. Regenerate the card framings with `uv run python -m tools.web_skill_cards` after re-running `tools.showcase_stills` and `tools.inspect_zone` as recorded in that file.

Motion: Lenis smooths wheel scrolling on the homepage only; Motion (`motion/react`, the Framer Motion package) drives the scroll-linked effects. The closing scene's timeline is `src/components/scene/timeline.ts`.
