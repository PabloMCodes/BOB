# B.O.B homepage redesign plan

Scope: the product homepage (`/`) in `web/`. The Dashboard route is a separate workstream. This plan extends [the hero, video and skills plan](../hero_video_skills_60a2f952.plan.md) and replaces its motion rules.

**Status (2026-10-10):** steps 2–9 are implemented in `web/` without the optional Claude Design step (the user chose to design directly in code). Build, lint, and a headless-browser screenshot pass at 1440px and 390px and with reduced motion have run. Physical-device checks (a real phone, Safari, trackpad feel of Lenis) have not. Every section whose content depends on the user (photos, hero media, team, GitHub link, YouTube ID) shows its empty state until that content is supplied.

## Goal

The page presents B.O.B the way [humanoperator.org](https://humanoperator.org/) presents its product: an innovation that changes how construction sites are inspected. A visitor should leave knowing what the robot does, who it helps, which parts work today, and which are still in development. The page ends with a 3D construction-site scene in which the robot inspects workers and marks every hazard category.

Bold framing is allowed; invented capability is not. Each feature carries one of two status tags, **Built** or **In development**. No percentages, no "makes the site safe", no "all clear".

## Decisions

| Topic | Decision | Source |
| --- | --- | --- |
| Brand | Wordmark **B.O.B**, expansion **Building-site Observation Bot** | Earlier plan, confirmed |
| Story | What the robot does and who it helps, framed as an innovation for construction sites | User, 2026-10-10 |
| Skill cards | The user's own photos of the robot and its bounding boxes, one card per AI skill, including alerts | User |
| Card look | Light band with white rounded cards (image on top, title, one short line), as on humanoperator.org; the rest of the page stays dark | User |
| Video | Editable `youtubeId`, empty by default, with a labelled empty state | Earlier session |
| 3D scene | At the end of the page. The rover is shown as an autonomous vehicle, labelled in development | User |
| Hazards in scene | All of them: PPE, person in path, restricted zone, walkway obstruction, plus Unverified and No hazard | User |
| Motion stack | Lenis (smooth scroll) and Framer Motion (now published as `motion`, same API) | User |
| Branch | `main` | Default integration branch |

Recommendations not yet confirmed by the user:

- The 3D scene is driven by scrolling while pinned on desktop, and plays as a loop on phones.
- Lenis smooths the mouse wheel only, leaving touch scrolling native on phones.
- At push time, AGENTS.md asks for a PR into `main` rather than a direct push.

## Page order

1. Header
2. Hero
3. Video
4. What B.O.B is (one paragraph)
5. Skills catalog (light band)
6. Who it helps
7. How it works (system line: iPhone, rover computer, operator laptop)
8. Inspection steps (the existing five agent steps)
9. 3D construction-site scene
10. Credits and closing claim

The existing worker-photo chapter merges into the skills catalog. Its measured-box overlay is kept for any photo supplied without burned-in boxes.

## Sections

### Header
Transparent over the hero. After 10px of scroll it becomes `canvas` at 90% opacity with a blur and a hairline, as on humanoperator.org. Links: Product, Dashboard, and GitHub once a public URL is given.

### Hero
- Content: large **B.O.B**, the expansion line, the headline, then a longer paragraph saying what the robot does and who it is for. Headline options for the user to choose from:
  - "A second set of eyes on every site walk."
  - "We sent AI on the site walk."
  - "See the worksite. Know what is still unknown." (current)
- Background: a full-bleed photo or muted looping video from `media.heroBackground`, under a dark overlay. Without media it falls back to a plain `canvas` background.
- Motion:
  - On load, the wordmark letters rise in a stagger, and the headline lines rise out of a mask over 900ms.
  - While scrolling through the hero, the background moves at about 0.4× scroll speed and scales from 1.0 to 1.08. The text moves up faster and fades out by 60% of the hero height, and the overlay darkens.
  - If the background photo has measured boxes, a single scan line sweeps across it once on load and the boxes draw in behind it.

### Video
A rounded 16:9 frame using `youtube-nocookie.com`, `rel=0`, no autoplay. An empty `youtubeId` shows a labelled empty state. Motion: as the frame enters the viewport it scales from 0.92 to 1 and its corner radius eases from 28px to 16px.

### What B.O.B is
One paragraph in a large type size. Each word goes from 20% to 100% opacity as the paragraph scrolls past.

### Skills catalog (light band)
Card structure copied from humanoperator.org:
- a white card with roughly 16px corner radius and a zinc border
- media on top at about 4:5
- a semibold title
- one muted sentence
- a status tag

Card list. **Trimmed to five for the demo (2026-10-11, user decision):** PPE, eyewear from far away, restricted zones, alert, drives itself. The other four rows below were removed from `copy.ts`; person-in-path and walkway obstruction still appear in the 3D scene. The original candidate list:

| Card | Sentence draft | Status |
| --- | --- | --- |
| Sees people and their PPE | Helmet, vest, gloves, eyewear and boots, boxed on each person in frame | Built |
| Checks eyewear from far away | Full-resolution head crops, so a face across the site still gets checked | Built |
| Checks only what the site requires | Requirements are chosen per worksite; unchecked means not required | Built |
| Watches taped restricted zones | Yellow floor tape is recognized; a person's feet inside it is a finding | Built, physical test pending |
| Flags people in its path | A person in the robot's travel lane is marked, not just a person in view | In development |
| Notices blocked walkways | Change against a known-empty walkway shows what blocks the lane | In development |
| Raises an alert | Repeated observations become a confirmed incident with its evidence | Built (incident policy); speaker alert on bench only |
| Keeps the evidence | Frame, session and model stay attached, then sync to the operator's laptop | Built |
| Drives itself | The rover is becoming an autonomous inspection vehicle | In development |

Motion:
- **Wide screens (1024px and up):** the band pins while vertical scroll moves the cards sideways. The section first holds still for about 22% of the viewport height, and cards move at roughly 1 px for every 1.85 px scrolled, the same numbers humanoperator.org uses. Left and right edge fades appear when there are cards off screen on that side.
- **Narrow screens:** swipe with snap points.
- **Card video:** clips play muted and looping only while the card is visible.
- **Card images:** each image drifts slightly inside its card. Any box overlay moves with the image, so the boxes stay aligned.

### Who it helps
Four tiles that rise in a stagger:
- **Site safety managers:** see which PPE checks were made and which could not be.
- **Superintendents:** spend less of the walk on routine looking.
- **Crews:** checked by a camera, not singled out by a person.
- **Owners and inspectors:** get a record that a later change of rules cannot rewrite.

The user confirms or edits the audience list.

### How it works
A line runs through three nodes: iPhone capture, then the rover computer (Mac today, Jetson planned), then the operator laptop with its dashboard and 2D Twin (planned UI). The line draws itself as you scroll, each node lights up when the line reaches it, and every node carries a Built or In development tag. Content comes from the README system overview.

### Inspection steps
The five existing steps, laid out with a title that stays on screen and a progress line that fills as you read. The active step is at full opacity and the others at 35%.

### 3D construction-site scene
- **Ground and structures:** a gravel pad with tire tracks, a poured slab, a half-built steel frame, scaffolding, and a crane or excavator silhouette in the background.
- **Site objects:** jersey barriers, cones, fencing with green screen, pallets of block, a floodlight tower, and a marked walkway.
- **Restricted zone:** yellow floor tape plus posts with yellow-and-black tape.
- **Light:** warm late-day sun with soft contact shadows. No high-resolution shadow maps and no post-processing.
- **Workers:** wear hard hats, hi-vis vests, gloves, safety glasses and boots, with variations that create one case of each mark.

| Worker or object | Mark | Label |
| --- | --- | --- |
| Worker without eyewear | hazard | Hazard · PPE · Eyewear |
| Worker without hard hat | hazard | Hazard · PPE · Helmet |
| Worker crossing the rover's lane | hazard | Hazard · In path |
| Worker inside the taped zone | hazard | Hazard · Restricted zone |
| Pallets across the walkway | hazard | Hazard · Walkway blocked |
| Worker half-hidden by scaffolding | unverified | Unverified · Not assessed |
| Fully equipped worker off the lane | clear | No hazard |
| Materials and barriers | clear | No hazard |

- **Rover:** a stylized autonomous vehicle with the iPhone on its mast. A translucent camera cone shows what it sees. When the cone reaches a worker, a box draws around the head or body region with that worker's label. The rover does not stop for anyone, because no hazard-stop behavior is built.
- **Robot's-eye view:** a small inset renders the camera's view with 2D boxes.
- **Chips:** `ILLUSTRATION` and `Autonomous driving · in development`.
- **Motion, desktop:** the section pins for about 400vh. Scroll progress drives the rover along its lane, the camera keyframes (a wide establishing shot, then over the rover's shoulder, then top-down) and when each label appears. The top-down end frame turns into a flat map labelled `2D Twin · planned`.
- **Motion, phones:** a timed loop of the same pass.
- **Reduced motion:** one settled frame with every mark visible.
- **Rendering limits:** one canvas. Scroll progress is read inside the frame loop, never through React state. The loop pauses when the scene is off screen. A WebGL failure falls back to the existing sentence.

### Credits
The closing claim in large type, the team members and their roles, the Knight Hacks credit, GitHub, and the license notes for SH17, Ultralytics and Roboflow data where the page shows their output.

## Motion rules (replace the current Motion.md rules)

- Lenis smooths wheel scrolling on the window. It is off under `prefers-reduced-motion` and does not touch native touch scrolling. Pinned sections use CSS `position: sticky` inside a tall wrapper, so they do not depend on Lenis.
- Scroll-linked values come from Framer Motion (`useScroll`, `useTransform`). The 3D scene reads the same progress value inside its frame loop.
- Parallax, pinned sections and looping muted card video are allowed. Zooming a photo inside its own crop is not, because burned-in or measured boxes would drift.
- Entrances: 700ms, `cubic-bezier(0.22, 1, 0.36, 1)`, a 16px rise, 80ms stagger capped at 400ms. These are kept from the current spec.
- Reduced motion: no smooth scroll, no parallax, no pinning (sections stack normally), a static scene frame, and all content present.

## Implementation steps

0. Run `git pull --ff-only` on `main`. `web/` is still untracked, so the first commit will add the whole app (only when the user asks for a commit).
1. Optional: static design frames in Claude Design for the hero, the skills band and a scene storyboard, at desktop and phone width.
2. Rewrite `web/Design.md` and `web/Motion.md` to match this plan.
3. Add the `lenis` and `motion` dependencies. Build the smooth-scroll provider, reduced-motion handling, a `Reveal` built on Motion, and the header scroll state.
4. Build the hero, video and overview sections.
5. Build the skills catalog with the media manifest (`media.skills[]`: `src`, `kind` image or video, `alt`, optional `boxes`).
6. Build the "who it helps", "how it works" and inspection steps sections.
7. Rebuild the 3D scene.
8. Build the credits section.
9. Checks:
   - `npm run build` and `npm run lint`
   - a browser pass at 1440px and 390px
   - a reduced-motion pass
   - the 3D scene holding 60 fps on the Mac
   - no horizontal page scroll

## Inputs needed from the user

- Photos and clips in `web/public/media/skills/` and `web/public/media/hero/`, plus which skill each one shows and whether its boxes are burned in.
- Confirmation that the people in the photos agree to appear on a public page.
- Team names and roles, the Knight Hacks wording, and a public GitHub URL if there is one.
- Headline choice, and a YouTube ID when the video exists.
