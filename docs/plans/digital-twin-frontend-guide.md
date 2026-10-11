# Dashboard: local connection and manager workflow

## Implemented data path

The phone sends frames and ARKit pose to `vision.server`. The shared Python pipeline produces detections and per-rule verdicts; `EdgePublisher` stores observations, evidence, camera track and the latest live state through the bounded writer. The edge sync API feeds the laptop hub's replicas. The browser talks only to that hub.

`web/src/dashboard/` implements the operator view. It displays incoming frame FPS, detection throughput Hz, pose-update Hz, inference time, detection confidence (%), frame drops, connection ages, model/rule capabilities, writer health, camera preview, worksite requirements, recorded assessments, detections, incident transitions, evidence downloads and operational logs. The existing `web/src/twin/` draws one ARKit session at a time. A pin is the observing camera's location, not the detected person's location.

| Hub route | Dashboard behavior |
| --- | --- |
| `GET /v1/status?workspace=…` | Connections, capabilities, preview metadata and measured telemetry |
| `GET /v1/preview/latest?workspace=…` | Authenticated, latest annotated image; SHA must match its metadata |
| `GET /v1/worksites`, `GET /v1/worksites/{id}`, `PUT /v1/worksites/{id}` | Read and save rover worksite requirements with `expected_revision` |
| `GET /v1/inspections?workspace=…` | Active/recorded inspection and bound profile revision |
| `POST /v1/inspections`, `POST /v1/inspections/{id}/end` | Explicitly start/end a rover inspection; the hub forwards it to the edge |
| `GET /v1/observations?latest=true&limit=30&workspace=…` | Recent detection boxes, each confidence and backend frame assessment |
| `GET /v1/incidents?latest=true&limit=30&workspace=…` | Recent backend policy transitions, end reasons and calibration labels |
| `GET /v1/evidence/{sha256}?workspace=…` | Evidence download; `202` means syncing, `404` means missing |
| `GET /v1/logs?limit=50&workspace=…` | Recent notices, incidents, profile/inspection events and recorded gaps; `before` pages backwards |
| `GET /v1/twin/sessions`, `…/{id}/track`, `…/{id}/pins` | Session selector, separated track segments, camera marker, observations and unlocalized items |

Read routes use the selected `workspace=rover|sample`. Worksite and command routes are rover-only; the UI refuses them in SAMPLE. Changing the connection or workspace clears the previous view and cancels its requests. Changing the selected session clears the map and detection/incident selection. The browser uses REST polling; the backend's existing `WS /v1/live` remains available to other consumers.

## Measured telemetry and unknown states

`bobapp/edge/publish/metrics.py` maintains bounded two-second windows on the rover monotonic clock. Incoming FPS counts admitted frame packets, pose Hz counts admitted frame plus standalone pose packets, and processing Hz counts completed frames. Rates are unknown during the initial window and fall to zero when no events arrive. A new session resets the windows and the last confidence/inference measurement. Confidence is the arithmetic mean of model-box scores in the latest processed frame, excluding derived violation boxes; individual box scores remain available in history. No model boxes means unknown confidence.

The writer publishes at most one `notice` with `code="stream_metrics"` per second through the existing extensible `bob-app` v1 envelope. No frozen CV v2 or application contract fields were changed. The hub adds optional `telemetry` and `telemetry_reason` to its status API, matches the active workspace/run/session, and labels metrics current only for realtime delivery and a current link with measurement age below three seconds. Age combines the rover's own monotonic age with time since receipt on the hub; clocks on different devices are never subtracted. Missing or malformed metrics do not hide link/capability information. The regenerated API contract is `schema/app/hub-openapi.json`.

The UI blanks current metrics on stale status and blanks latest inference/confidence when the result feed is old. Recorded detections remain history. Tracking loss leaves a path gap; invalid-pose findings stay off-map. Disconnecting preserves the last synced map with camera position unknown. An empty Rover workspace stays empty. SAMPLE never substitutes for it, and SAMPLE fixture history does not invent live FPS/Hz.

Status polls 500 ms after completion; other panels poll after 1.5 seconds. Each poll has one request in flight, a six-second timeout and a separate three-second stale deadline. Hidden tabs slow polling to five seconds. Commands are never automatically retried. An ambiguous command failure tells the operator to refresh inspection state before retrying.

## Site-manager requirements

1. Connect to **Rover** and select or create a worksite.
2. Select helmet, eyewear, high-visibility vest, gloves and safety boots as required or not required. Availability is reported by the running backend's model rules. Selecting an unsupported requirement is allowed, but its assessment remains unavailable; the UI never substitutes a similar model class.
3. **Save requirements** creates a new backend revision using the expected previous revision. Concurrent edits return a conflict; reload the saved requirements before editing again. An existing inspection continues under its original revision, and a newer revision is labeled pending.
4. With a current LIVE or REPLAY publisher connected, explicitly choose **Start inspection**. The request binds the saved worksite ID, revision and source mode. Unsaved edits, an existing inspection or an unavailable producer prevent a start from the UI.
5. Review backend assessment statuses and evidence, then explicitly **End current inspection**. The controls do not move the rover or clear a safety fault.

Unchecked means not required. An empty requirements selection does not establish compliance. Missing detections, tiny subjects, occlusion and unsupported classes remain not assessed or unavailable according to the backend; the frontend does not derive its own PPE verdicts. The optional footwear specialist must be enabled in the vision configuration to assess boots (`--config configs/footwear.yaml`); see its model card and acceptance limits.

## Run on this Mac

Use separate terminals from the repository root. Reuse existing services and stores rather than rebuilding them.

```bash
uv run python -m vision.server --detect --record --edge
uv run python -m bobapp.edge.api
uv run python -m bobapp.hub serve
```

Then in `web/`:

```bash
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `/dashboard`, expand **Connection settings**, retain `http://127.0.0.1:8780`, choose **Rover**, enter the token configured by the hub's `api.token_env` (default `BOB_EDGE_TOKEN`), and **Connect**. The token stays in page memory and travels in an Authorization header; it is never placed in a URL, browser storage or `VITE_*` variable. Refreshing the page requires entering it again.

The default Vite development hub connection uses a same-origin `/_bob/hub` proxy, including when the development server runs on another port. `VITE_HUB_URL` can set the configured default hub address. A different address typed into Connection settings uses direct requests and must permit the browser origin in the hub's `api.cors_origins` override. A production static build (`vite preview` included) uses direct requests; configure that origin or an authenticated reverse proxy, because Vite's development proxy is not deployed in `dist/`.

On this Mac the existing production preview is `http://127.0.0.1:4317/dashboard`. Its exact origin was added to the gitignored `configs/hub.local.yaml` while preserving the other settings and token requirement. The hub, rover edge API and pinned SH17 vision server are running; both hub workspaces connect, and the vision server is waiting for an iPhone on port 8765. No phone frames or real inspections were fabricated. Refresh the dashboard and enter the hub token to connect the browser.

Hub defaults: edge `ws://127.0.0.1:8770`, API `http://127.0.0.1:8780`. Overrides belong in `configs/hub.local.yaml`; do not append `/v1/sync` to `edge_url`. The edge API and vision publisher must use the same edge store configuration. An available hub without a running edge/phone stream correctly shows disconnected/unknown Rover data.

Optional SAMPLE: use the already configured separate sample service (`uv run python -m bobapp.edge.api --edge-config configs/sample-edge.yaml`), then select **SAMPLE**. `uv run python -m bobapp.sample` rebuilds its dedicated store and should be run only when intentionally replacing demonstration data. It never populates Rover.

## Verification and remaining acceptance

- Full Python suite: 542 passed, with two existing dependency warnings. Six new tests cover measured rates/warmup/session reset, model-only confidence, authenticated workspace-scoped logs, backward paging, latest history, link/run/delivery freshness, combined metric age and malformed optional telemetry. Existing worksite tests verify exact revision binding and edge command forwarding.
- In `web/`: `node --test tests/twin.test.ts tests/twin-map.test.mjs tests/dashboard.test.ts`: 15 passed (Node 26). Checks include five requirement values, revision-bound explicit commands, SAMPLE command refusal, authentication/cancellation, workspace/session isolation, uncertainty and map rendering.
- `npm run build`: typecheck and production build pass; the existing lazy-loaded 3D homepage scene emits a bundle-size warning.
- API/frontend-client checks verify SAMPLE preview, 70 track points in two segments, placed and unlocalized observations, 15 confidence-bearing detection frames, incident/log history, and an empty separate Rover. Temporary manager profiles verify all five selections, a helmet toggle, immutable previous revisions and refusal to start without an edge. The real Rover edge/hub link is CONNECTED with no phone session; default boots capability is unavailable as expected. Development proxy and exact-origin production-preview CORS/PUT preflight checks retain token enforcement.
- Browser inspection verified dashboard layout and its authentication-required state. A complete interactive SAMPLE/manager browser pass remains a manual check; native browser interaction was interrupted by concurrent user activity. Physical iPhone walk, multi-device acceptance, worksite PPE accuracy and incident calibration remain pending.

These checks establish software integration, not a live phone or Jetson acceptance run. The frontend and backend keep unavailable producers visible rather than presenting planned capabilities as current feeds.
