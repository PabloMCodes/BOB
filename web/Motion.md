# Motion

How the homepage moves. Visual rules are in [Design.md](Design.md).

Motion carries the story: the page should feel like walking a site with the robot. Every effect must still read correctly with motion turned off.

## Stack

- **Lenis** smooths mouse-wheel scrolling on the window (`lerp 0.1`). Touch scrolling stays native. Lenis is not started under `prefers-reduced-motion: reduce`.
- **Motion** (the Framer Motion package, imported from `motion/react`) supplies scroll-linked values (`useScroll`, `useTransform`) and entrances.
- Pinned sections use CSS `position: sticky` inside a taller wrapper, so they work with or without Lenis. Pinning happens only from `1024px` up.
- The 3D scene reads the same scroll progress inside its frame loop. It never sets React state per frame.

## Shared entrance

Used by headings, paragraphs and tiles the first time they reach 20% visibility.

- `700ms`, `cubic-bezier(0.22, 1, 0.36, 1)`, rise `16px`, opacity `0` to `1`.
- Stagger `80ms`, capped so the last sibling starts within `400ms`.

## Header

Transparent at the top. After `10px` of scroll the background, blur and border fade in over `300ms`. The header never changes height.

## Hero

On load:

1. `Building-site Observation Bot` rises.
2. The letters of **B.O.B** rise out of a mask, `60ms` apart, `900ms` each.
3. The claim and paragraph use the shared entrance at `+320ms` and `+400ms`.

While the hero scrolls out (from its top at the viewport top until its bottom reaches the viewport top):

- The background moves down at 40% of the scroll distance and scales from `1.0` to `1.08`. It is a full-bleed background, not a photograph with boxes.
- The text block moves up `12%` faster than the page and fades to `0` by 60% of the way.
- The scrim darkens from `0` to `0.6` extra opacity.

The scroll cue's highlight travels down the `28px` line over `1.6s`, linear, repeating.

## Video

As the frame travels from the bottom of the viewport to its center, it scales `0.92` to `1` and its radius eases `28px` to `16px`.

## What B.O.B is

Each word goes from `20%` to `100%` opacity in reading order as the paragraph travels from 85% to 35% of the viewport height.

## Skills band

Wide screens:

- The band pins for `100vh + hold + overflow × 1.85` of scroll, where `hold` is `22vh` and `overflow` is how far the card track is wider than the viewport.
- During the hold the cards do not move. After it, the track moves left `1px` for every `1.85px` scrolled, until the last card is fully in view.
- A fade covers the left edge once the track has moved, and the right edge while cards remain off screen.
- Each card's media drifts horizontally `±4%` with the rail progress, inside its own frame. Box overlays move with the media.

Narrow screens: a native horizontal scroller with snap points on card starts. No pinning.

Card clips play only while the card is at least 30% visible, and pause otherwise.

## Who it helps

Tiles use the shared entrance with the `80ms` stagger.

## How it works

As the section travels through the viewport, an `ink` segment draws along the connecting line from the first node to the last. A node switches its index from `muted` to `ink` when the segment reaches it.

## Inspection steps

The title stays pinned on the left while the steps scroll on the right (wide screens). A 1px progress line beside the steps fills with scroll. Each step's opacity follows its own position: `35%` as it enters the lower fifth of the viewport, `100%` through the middle, back to `35%` as it leaves the top fifth.

## Closing scene

Wide screens with motion allowed: the scene section pins for `400vh`. Scroll progress `p` from `0` to `1` drives everything. Phones: the same pass plays on a `20s` clock from `p = 0` to `p = 0.72`, holds for `2s`, and starts again behind a `400ms` fade to `canvas`. Reduced motion: one settled frame (`p = 0.66`) with every mark visible and no inset motion.

| `p` | What happens |
| --- | --- |
| `0.00–0.08` | Establishing shot from high front-left. The whole pad is readable before any mark. |
| `0.05–0.70` | The rover drives up its lane with eased start and stop. Its wheels turn with distance. |
| `0.12` | Hazard · PPE · Eyewear |
| `0.20` | Hazard · PPE · Helmet |
| `0.28` | Hazard · In path |
| `0.36` | Hazard · Restricted zone |
| `0.44` | Hazard · Walkway blocked |
| `0.52` | Unverified · Not assessed |
| `0.58` | No hazard (worker) |
| `0.62` | No hazard (materials) |
| `0.10–0.40` | The camera eases from the establishing shot to over the rover's shoulder and follows it. |
| `0.40–0.66` | The camera pulls back to a wide three-quarter view. All eight marks are readable together. |
| `0.74–0.90` | The camera rises to a top-down view. Labels and the inset fade out. |
| `0.84–0.94` | The 2D Twin overlay fades in: the path draws, then one dot per finding at the robot's position when it observed that subject. |

Each label fades in over `0.025` of progress and stays. A mark is never relabeled. The inset draws a subject's box when that subject's label appears.

Labels are placed in reveal order. A label that would cover an earlier one moves up just far enough to clear it, and a thin leader line in its mark color runs down to its subject. Labels never leave the canvas edge; the leader line still points at the subject.

### Scene performance

- One canvas, device-pixel ratio capped at `1.5`. The main view and the inset are two renders of the same scene in one frame.
- The loop stops when the section is off screen.
- If WebGL cannot start, the section shows its title and "This illustration could not start in this browser."

## Reduced motion

`prefers-reduced-motion: reduce` turns off Lenis, parallax, pinning (pinned sections lay out as ordinary stacked sections), the word fill (words at full opacity), the scroll cue travel, box drawing and the scene clock. All content is present.

## Inspiration scroll

`/inspiration` uses the existing Framer Motion runtime (`motion/react`) with native scrolling. A 1px reading-progress line below the navigation follows page progress through a spring (`stiffness: 120`, `damping: 30`). The introduction shifts upward by up to `60px` and fades to `60%` as it leaves the viewport.

The main heading emphasizes the shared build. Its words rise from below a clipping mask (`110%` to `0`, rotation `3°` to `0°`) over `950ms`, staggered by `90ms`. One stable heading triggers the sequence, and assistive technology receives one complete heading.

Each chapter draws its top rule over `900ms` and reveals its heading and story from `32px` below over `700ms`. Photo frames rise `40px` over `800ms`, with a `100ms` stagger between adjacent photos. Real photos also move vertically from `−2%` to `2%` of their height with scroll, scaling from `95%` to `100%` and back so the whole image stays inside its box. Placeholders keep their empty state.

The build, connection and rover chapters pair a real challenge with the team’s response. These columns rise `24px` over `700ms`, with a `160ms` stagger from challenge to response. Suggested mitigation copy carries a visible **Draft team notes** label until the team confirms it.

Near the end, a team signature draws three paths from Humberto, Pablo and Maham into one shared B.O.B. Each path draws over `1200ms`, staggered by `120ms`; the shared stem and wordmark follow. This is a symbolic collaboration graphic, separate from the globe’s geographic routes. It plays once.

The globe rises `64px` and grows from `88%` over `1100ms`; teammate cards enter from `28px` to the right and `16px` below, growing from `96%`, over `800ms` with a `120ms` stagger. Entrances play once. Globe controls remain visible, and keyboard focus reveals a teammate card immediately. Reduced motion shows all content at full opacity without entrance animations, path drawing, photo parallax, introduction movement or the progress line. Mobile layouts use the same small movements without pinning or scroll interception.

## Inspiration globe

Near the end of `/inspiration`, the globe rotates slowly while visible and the page is foregrounded. Dragging changes its orientation; manual rotation buttons offer the same action from a keyboard. Pause/resume controls stop automatic rotation. Hovering, focusing or pinning a teammate frames their origin and Florida, stops automatic rotation, lights their country and shows only their route. Leaving the card restores the pinned selection or all connections. Reduced motion disables auto-rotation and camera transitions; deliberate manual rotation remains available. Offscreen and background rendering stops. WebGL or texture failures use a static SVG with the same teammate selections.

## What never moves

- Box coordinates relative to their photograph.
- The header's size.
- Data. This page opens no socket and polls nothing.
