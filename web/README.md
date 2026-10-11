# BOB product page

Local Vite app for the product page and the operator dashboard at `/dashboard`. The dashboard connects to the laptop hub for measured FPS/Hz/confidence, preview, connections, backend logs, detections, incidents, evidence and a session-specific digital twin. Site managers can save the five PPE requirements and explicitly start/end an inspection using a saved revision. SAMPLE is a separate read-only workspace.

See [the digital twin integration guide](../docs/plans/digital-twin-frontend-guide.md) for startup, authentication, data semantics and verification. The default hub is `http://127.0.0.1:8780`; connection settings allow a different address. An optional `VITE_HUB_URL` sets the initial address, never a token.

Read [Design.md](Design.md) before changing layout or color. Read [Motion.md](Motion.md) before changing scroll, the detection boxes, or the closing scene.

```bash
npm install
npm run dev
```

`npm run build` typechecks and writes `dist/`. `npm run lint` runs oxlint. Run the dashboard client checks with `node --test tests/twin.test.ts tests/twin-map.test.mjs tests/dashboard.test.ts` (Node with native TypeScript support).

The Vite development server proxies the configured default hub through `/_bob/hub`, including Authorization headers, so development previews on any local port can connect without changing the hub's CORS settings. A different address entered in Connection settings is accessed directly and must allow the browser origin. Production builds (`vite preview` included) must configure CORS or their own authenticated reverse proxy; the development proxy is not part of `dist/`.

## Filling in the homepage

The section plan is [docs/plans/homepage-redesign-plan.md](../docs/plans/homepage-redesign-plan.md).

| What | Where |
| --- | --- |
| Headline, paragraphs, card text, team, GitHub link, YouTube ID | `src/data/copy.ts` |
| Hero background (photo or clip) | file in `public/media/hero/`, entry `heroBackground` in `src/data/media.ts` |
| Skill card photos or clips | files in `public/media/skills/`, entries in `skillMedia` keyed by the card `id` |

A card without media shows a dark plate with its number. If a photo's boxes are already drawn into the file, leave `boxes` out. For a clean photo, list `boxes` as fractions of the original image (`x`, `y`, `w`, `h`, `label`), measured from the file.

Motion: Lenis smooths wheel scrolling on the homepage only; Motion (`motion/react`, the Framer Motion package) drives the scroll-linked effects. The closing scene's timeline is `src/components/scene/timeline.ts`.
