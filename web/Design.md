# Design

Visual rules for the B.O.B homepage and the Dashboard placeholder. Motion lives in [Motion.md](Motion.md). Wording lives in `src/data/copy.ts`. Photographs, clips and their boxes live in `src/data/media.ts`. The section plan is [docs/plans/homepage-redesign-plan.md](../docs/plans/homepage-redesign-plan.md).

The page follows the rhythm of [humanoperator.org](https://humanoperator.org/): one large claim, a video, a rail of skill cards, numbered steps, a closing scene and credits. The words, photographs and scene are B.O.B's. B.O.B is a construction-site inspection robot. It checks people for the PPE a worksite requires, watches marked zones, keeps the original frame with every finding, and keeps visible what it could not establish.

Bold framing is fine. Invented capability is not. Every feature that is not working today carries the tag **In development**. No percentages, no time saved, no "makes the site safe", no "all clear".

## Routes

| Path | Role |
| --- | --- |
| `/` | Product story. One continuous scroll. |
| `/dashboard` | Same header and tokens. Read-only 2D twin using only `/v1/twin/` hub routes. Logs and other backend integrations are excluded. |

## Color

All colors are theme tokens in `src/styles.css`. Components do not carry hex values, except the 3D scene's materials, which live in one place in `src/components/scene/palette.ts`.

| Token | Value | Use |
| --- | --- | --- |
| `canvas` | `#070708` | Page background |
| `ink` | `#f3f2ee` | Headlines, active nav, photo-box stroke |
| `muted` | `#9b9a94` | Supporting sentences, inactive nav |
| `line` | `#2c2c2a` | Hairlines, header border |
| `band` | `#fafafa` | The skills band background only |
| `card` | `#ffffff` | Skill cards |
| `band-ink` | `#09090b` | Titles on the band |
| `band-muted` | `#52525b` | Sentences on the band |
| `band-line` | `#e4e4e7` | Card borders on the band |
| `band-plate` | `#ececee` | Empty media plate on a skill card |
| `hazard` | `#ff5c3a` | Closing scene only. A hazard mark |
| `clear` | `#8fd6b2` | Closing scene only. A no-hazard mark |
| `unverified` | `#c4bfb2` | Closing scene only. A subject that could not be assessed |
| `tape` | `#e2c15a` | Restricted-zone tape in the scene, and the In development tag on dark |
| `tape-deep` | `#8a6a12` | The In development tag on the light band |

Hazard red and clear green never appear on photographs. A box on a photograph shows where the robot looked, not a verdict.

## Type

DM Sans, shipped with the app as `DM Sans Variable`. The page requests no font from the network.

| Role | Size | Weight | Line height | Tracking |
| --- | --- | --- | --- | --- |
| Wordmark (hero) | `clamp(4.5rem, 16vw, 13rem)` | 600 | 0.86 | `-0.05em` |
| Hero claim | `clamp(2.25rem, 5vw, 4.25rem)` | 500 | 1.0 | `-0.035em` |
| Statement (overview) | `clamp(1.6rem, 3.2vw, 2.75rem)` | 500 | 1.18 | `-0.025em` |
| Chapter title | `clamp(2rem, 4.2vw, 3.4rem)` | 500 | 1.02 | `-0.03em` |
| Card title | `clamp(1.25rem, 1.65vw, 1.6rem)` | 600 | 1.05 | `-0.04em` |
| Step title | `clamp(1.5rem, 2.4vw, 2rem)` | 500 | 1.15 | `-0.02em` |
| Body | `1.125rem` | 400 | 1.5 | `0` |
| Card sentence | `0.875rem` | 400 | 1.6 | `0` |
| Labels, nav, tags | `0.8125rem` | 500 | 1.2 | `0.08em`, uppercase |

## Space

- Page inset: `clamp(1.25rem, 4vw, 4.5rem)` left and right.
- Header height: `4rem`, fixed.
- Wide layout from `1024px`. Below it, sections stack and nothing pins.
- Body copy max width `36rem`.

## Header

Left: wordmark `B.O.B`. Right: Product, Dashboard, and GitHub when `copy.links.github` is set.

Over the top of the hero the bar is transparent with no border. After `10px` of scroll it becomes `canvas` at 90% with a blur and a 1px `line` border.

## Status tags

A tag is the label type inside a 1px border, `0.2rem 0.45rem` padding.

- **Built**: `ink` on dark, `band-ink` on the band.
- **In development**: `tape` on dark, `tape-deep` on the band.

Tags appear on skill cards and on the system line. A feature with a working part and an unfinished part says so in its sentence and takes the tag of its least finished part.

## Sections, in order

### 1. Hero

One viewport.

- `Building-site Observation Bot` in the label type, then the **B.O.B** wordmark, then the claim, then a paragraph of two or three sentences.
- Background: `media.heroBackground` (photo or muted looping clip), `object-cover`, under a scrim from `canvas` at 35% (top) to 85% (bottom). With no media, a plain `canvas` field with a faint `line` grid.
- A scroll cue at the bottom left: `Scroll` and a short vertical line.

### 2. Video

A 16:9 frame with a `16px` radius and a 1px `line` border, inset by the page inset. `youtube-nocookie.com`, `rel=0`, no autoplay. With an empty `copy.video.youtubeId` the frame shows the label `Video coming soon` and nothing else.

### 3. What B.O.B is

One paragraph in the statement type, `ink`, max width `24em`. Eyebrow `What it is`.

### 4. Skills (the light band)

The only light section, imitating the humanoperator.org card rail. Five cards. Eyebrow and chapter title in `band-ink` scroll past first; the cards then pin on their own, vertically centered.

- The rail sits in a centered frame, max `80rem` inside the page inset, that clips the track. Fades in `band` cover its left and right edges (`clamp(3rem, 16%, 12rem)` wide) while cards are off screen on that side.
- Card: `card` background, 1px `band-line` border, `1.25rem` radius, overflow hidden. Width `min(27rem, (100svh − 20rem) × 0.8)` on wide screens, `min(80vw, 22rem)` on narrow ones. Gap `1.5rem`.
- Media on top at `4:5`. Without media, a `band-plate` panel with the card's index (`01`, `02`, …) in the label type. No stock image, no fake boxes.
- The status tag sits on the media, top left, as a white pill (`card` at 90%).
- Below the media: card title (`clamp(1.25rem, 1.65vw, 1.6rem)`, 600, `-0.04em`) and one sentence (`0.875rem`, line height 1.6) in `band-muted`. Padding `1.25rem 1.25rem 2rem`. Nothing else.

Media rules:

- `kind: 'image'` or `kind: 'video'` (muted, looping, inline, no controls).
- Boxes already drawn into the file: leave `boxes` empty.
- Boxes measured on a clean file: list them as fractions of the original image (`x`, `y`, `w`, `h`, `label`). They are drawn over the image in `ink`, 1.5px, with a `canvas` label chip, and they move and crop with the image.

### 5. Who it helps

Eyebrow `Who it helps`, chapter title, then four tiles in a 2×2 grid on wide screens (one column on narrow). Each tile: a `line` top border, the audience in the step-title type, one sentence in `muted`.

### 6. How it works

Eyebrow `How it works`, chapter title, then three nodes on one line on wide screens (a vertical line on narrow): iPhone capture, rover computer, operator laptop. Each node: index, title, one sentence, status tag. The connecting line is 1px `line`, with an `ink` segment drawn over it as the reader scrolls.

### 7. Inspection steps

Eyebrow `How the record is made`. On wide screens the title stays on the left while the five steps scroll on the right, with a 1px progress line beside them. Narrow: title, then steps.

### 8. Closing scene

Eyebrow `On a site` and title in the page flow, then the canvas. Detection labels live in an overlay above the canvas. Two chips at the top right of the canvas: `Illustration` and `Autonomous driving · in development`. This is not the live twin.

The world:

- Gravel pad with tire tracks, a poured slab with a half-built steel frame, scaffolding, a crane mast and jib in the distance, a yellow excavator, jersey barriers, cones, a fence with green screening, block pallets, a floodlight tower.
- A pedestrian walkway with painted edges, and a restricted zone of yellow floor tape with posts and striped tape.
- Workers in work clothes. Variations put on or take off hard hat, hi-vis vest, gloves, safety glasses and boots.
- B.O.B as a stylized autonomous rover: chassis, four wheels, a mast with the iPhone, a translucent camera cone ahead of it. It is not a model of the real machine.
- Late-day light: a warm low sun, a cool sky fill, a fog that fades the edges into `canvas`. No shadow maps, no post-processing. Soft dark ellipses under people and objects stand in for contact shadows.

Marks:

| Subject | Mark | Label |
| --- | --- | --- |
| Worker without safety glasses | `hazard` | Hazard · PPE · Eyewear |
| Worker without a hard hat | `hazard` | Hazard · PPE · Helmet |
| Worker standing in the rover's lane | `hazard` | Hazard · In path |
| Worker inside the taped zone | `hazard` | Hazard · Restricted zone |
| Pallets across the walkway | `hazard` | Hazard · Walkway blocked |
| Worker half hidden by scaffolding | `unverified` | Unverified · Not assessed |
| Fully equipped worker off the lane | `clear` | No hazard |
| Barriers and stacked materials | `clear` | No hazard |

Label chips: uppercase, 11px, 1px border and text in the mark color, `canvas` at 72% behind. Unverified chips use a dashed border. A person in view is not automatically in the path: only the worker in the lane gets that label. The rover does not stop for anyone in the illustration, because no hazard-stop behavior is built.

Robot's-eye inset: a 4:3 frame at the bottom right of the canvas (bottom left on narrow), 1px `line` border, label `Robot's-eye view`. It shows the iPhone camera's view with a 1.5px box around each revealed subject in its mark color.

The scene ends top-down. A 2D map overlay draws the rover's path and one dot per finding **at the point on the path where the robot made the observation**, not at the subject, with the chip `2D Twin · planned`.

### 9. Credits

The closing claim in the chapter-title type, `A Knight Hacks project.`, the team list when `copy.credits.team` has entries (name and role, nothing invented), GitHub when set, and the model and license line.

## Dashboard twin

The dashboard uses the existing dark theme with a responsive map and details panel. Draw the camera path in ink, backfilled history dashed, and observation pins in tape. A disconnected view preserves history and labels the position unknown. Sessions and sample/rover workspaces must never be overlaid. Pin numbers connect map locations to their descriptions; unlocalized items stay off-map. No motion or safety controls.

## Out of scope on the product page

Live, replay and sample data. Hub calls. Incident lists. Requirement checkboxes. Any control that would move the rover or clear a fault.
