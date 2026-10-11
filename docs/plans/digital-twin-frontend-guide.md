# Digital twin pane: local integration

## Scope

`/dashboard` reads the existing laptop hub's 2D twin models. It shows one ARKit session at a time: camera track, heading and position status, observation pins, and observations without valid positions. Pins locate the observing camera, not the person or hazard. This is an advisory view.

Only these read-only routes are called, all with the same `workspace=rover|sample`:

| Route | UI |
| --- | --- |
| `GET /v1/twin/sessions` | Session selector and source labels |
| `GET /v1/twin/sessions/{id}/track` | Separate path segments, with dashed backfilled history |
| `GET /v1/twin/sessions/{id}/pins` | Camera marker, numbered observations and unlocalized items |

No logs, broader live feed, video, evidence downloads, inspection controls, model loading, backend/schema changes, or rover commands are included. The existing backend models are in `bobapp/hub/api/models/twin.py`; frontend types mirror only the fields used here.

## Run on this Mac

1. **Make data available.** Keep the existing rover/recording producer running with edge publication enabled. If the edge service is not running, start `uv run python -m bobapp.edge.api` from the repository root. Existing live capture uses `uv run python -m vision.server --detect --record --edge`; recorded verification should use the existing replay workflow. Model weights alone do not provide a camera path: the twin needs published pose records.
2. **Start the hub:** from the root run `uv run python -m bobapp.hub serve`. Defaults are edge `ws://127.0.0.1:8770` and hub `http://127.0.0.1:8780`. Local overrides belong in `configs/hub.local.yaml`; do not append `/v1/sync` to `edge_url`. Set `sample: {edge_url: null}` there if no sample service is used.
3. **Start the website:** in `web/`, run `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`, open `http://127.0.0.1:5173`, and click **Dashboard** in the header. Direct access at `/dashboard` works too. Dependencies must already be installed (`npm install` if absent).
4. **Connect:** expand **Connection settings**, retain `http://127.0.0.1:8780`, select **Rover**, and click **Connect**. If the hub requires authentication, enter the token corresponding to `api.token_env` in its config (default `BOB_EDGE_TOKEN`). The page keeps it in memory and sends an Authorization header. Do not embed a token in a `VITE_*` variable or URL. The default hub CORS configuration already permits port 5173 on localhost and 127.0.0.1.
5. **Select data:** follow the current session, or explicitly choose historical data. If there is no current session, automatic selection uses the last session returned by the hub. Each refresh loads sessions, then the selected track and pins together. The next refresh starts 1.5 seconds after completion; requests time out after 6 seconds. Without a successful refresh for 3 seconds, the displayed position becomes unknown even while a request is pending. Switching connections or sessions discards the old map and cancels outstanding requests.
6. **Check the result:** tracking loss must leave a path gap; a new session must use a separate map; invalid-pose observations must remain off-map; backfilled history must be dashed. Disconnecting the hub must retain the previous map as stale, with current position unknown. An empty workspace shows an empty state, never invented data.

Optional demonstration: select **SAMPLE** only if the separate sample edge/workspace is already configured and populated. The existing sample service runs with `uv run python -m bobapp.edge.api --edge-config configs/sample-edge.yaml`. Generating it with `uv run python -m bobapp.sample` **rebuilds the dedicated sample store**, so do that only when intentionally replacing its demonstration data. It never belongs in the rover workspace.

## Verification and limits

- `uv run pytest`: 536 passed (two existing dependency warnings).
- In `web/`: `node --test tests/twin.test.ts tests/twin-map.test.mjs`: 10 passed, checking website navigation/pane rendering, request scope, authentication, session/workspace isolation, tracking gaps, backfilled rendering, heading, stale marker and escaped labels. Requires a Node release with native TypeScript support; verified with Node 26.
- `npm run build`: passes for the complete website (existing 3D scene bundle size warning). The homepage's missing empty photo collections/types and obsolete worker-copy references were repaired so the website can reach the dashboard. Product content is loaded separately from the twin.
- The real FastAPI twin routes were exercised through the frontend client using isolated temporary sample stores: 70 track points in two segments, four placed observations, one unlocalized observation, and an empty separate rover workspace. `/dashboard` returned HTTP 200. Existing stores were untouched.
- Browser visual verification and the physical iPhone walk remain manual checks. A test fixture is not evidence of a live device connection.
- No changes have been committed, pushed or deployed.
