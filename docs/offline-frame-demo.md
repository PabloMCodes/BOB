# Wi-Fi loss and automatic frame recovery demo

BOB now saves a clean upright JPEG for **every processed model frame**, with its
original detections, frame/session ID and receiver timestamp, whether the laptop
is connected or disconnected. On reconnection, the laptop hub resumes its saved
cursors, downloads missing JPEGs, verifies their hashes, and confirms each saved
image to the Jetson. Interrupted downloads retry automatically. Repeated connections
do not duplicate observations.

The dashboard keeps **Camera preview** separate from **Saved camera frames →
Recovered history**. The latter fills automatically as images arrive, with the
original boxes and separate BOB capture / laptop receipt times. Backfilled images
are history, never labeled as current conditions. First connection also counts
existing records as recovered history; the label alone does not prove a Wi-Fi outage.

## Demo topology

```text
iPhone ── local Wi-Fi ── Jetson (models + durable frame archive + edge API)
                             │
                             └── Wi-Fi ── laptop hub ── website in browser
                                  ↑
                         disconnect this link only
```

Keep the phone and Jetson connected to their router/hotspot. Turn off **only the
laptop's Wi-Fi**. If the laptop itself is providing the hotspot, turning it off
also interrupts the phone camera stream; use an independent router/hotspot for
this demo. The local models do not require internet, but they still require camera
frames. Turning off only the router's internet uplink may leave local synchronization
working normally, so it does not demonstrate a laptop-to-rover outage.

## Start the processes

Use the updated backend on **both Jetson and laptop**, plus the updated website.
This change does not deploy to a hosted website or install boot services. No BOB
vision/edge/hub systemd services were installed on this Jetson during verification.

1. Set the same `BOB_EDGE_TOKEN` in each machine's gitignored `.env`. Do not put
   tokens in Git or paste them into logs. The edge API binds to loopback without
   a token; it needs a token for laptop access.
2. Run the working vision command on the Jetson with `--edge` added, and start
   the edge API against the same edge config/store. Preserve the model/config/
   zone flags you already use. Stop an older process on the same port first.
   **Detach these processes from SSH**, otherwise closing the laptop connection
   may terminate the process during the demo. Example using the existing `.venv`:

   ```bash
   cd /home/pablo/BOB
   mkdir -p runs/offline-demo
   nohup .venv/bin/python -m vision.server --detect --no-view --edge \
     >> runs/offline-demo/vision.log 2>&1 < /dev/null &
   echo $! > runs/offline-demo/vision.pid
   nohup .venv/bin/python -m bobapp.edge.api \
     >> runs/offline-demo/edge-api.log 2>&1 < /dev/null &
   echo $! > runs/offline-demo/edge-api.pid
   ```

   If your current working vision command includes, for example,
   `--config configs/footwear.yaml`, keep it in the first command. If you specify
   `--edge-config`, use the same file for both processes. This is not a new model
   or a change to detector/PPE rules. Verify both logs show successful startup.
3. On the laptop, set `edge_url: ws://10.6.3.3:8770` in
   `configs/hub.local.yaml` (substitute the reachable Jetson address if it changed).
   Start the hub with the repository's normal Python environment:

   ```bash
   uv run python -m bobapp.hub serve
   ```

4. Start the website locally on the laptop with `cd web && npm ci && npm run dev`.
   Open the dashboard, choose the rover workspace and the laptop hub address
   (`http://127.0.0.1:8780`), and enter its token. Leave the tab and hub running.
   A public HTTPS website needs an appropriate HTTPS API/proxy and allowed origin;
   it cannot directly replace this local demo setup by pointing at an HTTP LAN
   address. The existing Vite development proxy supports the local setup.

Do not run `uv sync` on the Jetson: preserve its NVIDIA CUDA environment. The
Jetson default edge identity is currently `rover-mac`; both processes must use
that same identity/store unless you intentionally migrate it.

## Perform the demo

1. Stream from the iPhone and verify Camera preview updates. Check **All saved
   frames** to see frames with original detections. No inspection needs to be
   started merely to save frames; worksite assessment still requires its usual
   explicit inspection start.
2. Select **Recovered history**, note the last frame number, and turn laptop Wi-Fi
   off for 15–30 seconds. Previously loaded pictures remain visible. The UI reports
   lost contact; it does not pretend to know the rover's current state.
3. Present a visibly different scene during the disconnect while the phone keeps
   streaming to the Jetson.
4. Restore laptop Wi-Fi. No reload or upload button is needed. The hub reconnects,
   live preview resumes independently, pending image counts change and the missing
   pictures appear in the gallery. The **Older frames** button pages through longer
   backlogs. Original model boxes are overlaid on their matching saved JPEG.
5. Compare frame IDs and the recorded capture/receipt times. These times belong to
   different device clocks; do not subtract them as a network-latency measurement
   unless the clocks have independently been synchronized.

Closing only the website tab does not stop the hub: the hub can keep receiving
images, and opening the tab later shows those already saved locally. BOB never
waits for a browser before storing a processed frame.

## Capacity and remaining limits

- `configs/edge.yaml` enables `archive.enabled: true` by default when `--edge` is
  used. This captures processed model inputs, including frames without violations.
  It is not an archive of every raw iPhone frame: capture throttling and the
  existing latest-frame-wins inference policy still apply.
- JPEG quality uses `evidence.jpeg_quality` (90 by default); boxes remain metadata
  so the clean image and exact original detection result are both available.
- The default edge store budget is 2 GiB with a 1 GiB free-disk reserve. New frame
  images stop being saved at that threshold; existing untransferred images remain.
  `frame_archive_full` and `frame_archive` notices report the condition and skipped
  image count in Backend logs. Writer overload or storage errors are also explicit.
  No finite disk or bounded nonblocking queue can promise unlimited lossless capture.
- A record acknowledgment is **not** an image receipt. Frame records and shared
  JPEGs remain protected until known consuming hubs confirm verified copies; the
  normal acknowledged-age retention policy then applies. Older hubs without the
  new receipt endpoint retain images on the Jetson rather than deleting them early.
- Hub `blobs.max_bytes_per_s` defaults to 1 MB/s; reconnect backoff is 0.5–5 s,
  plus connection/HTTP timeouts. Gallery polling is once per second. Recovery
  begins automatically, but a large backlog takes time. For a fast local demo,
  measure the capture byte rate and LAN capacity before increasing the hub cap
  (for example to 4 MB/s in `configs/hub.local.yaml`). If new-image production
  exceeds transfer throughput, pending images will accumulate while streaming.
- JPEG encoding/storage runs on the bounded writer thread, never on the inference
  or Wi-Fi receive path. Disk failure cannot block inference indefinitely, but
  it can cause explicitly counted unsaved records. Uncommitted queue items can
  be lost on abrupt process/power loss; this change is not a power-loss guarantee.
- The hub replica/gallery survives process restarts. There is no automatic hub
  image-expiry job in this change; the existing operator-managed website deletion
  policy still applies. Do not delete the Jetson store directory between sessions.

## Verification

- Jetson full Python suite: **640 passed, 5 optional/platform skips**, 166.50 s.
- The controlled TCP outage test saved eight distinct JPEGs during the outage,
  recovered all eight in **0.62 s** after restoration on localhost, preserved the
  original event IDs/bytes and kept nine total observations after a second
  disconnect/reconnect. This is a small software test, not a Wi-Fi throughput result.
- Tests cover clean-frame storage without PPE findings, restart recovery, shared
  images, metadata-before-image acknowledgments, multiple hub receipts, capacity
  limits, authentication/epoch checks, partial/corrupt downloads, pagination and
  separation of sample and rover data. Run:

  ```bash
  YOLO_AUTOINSTALL=false .venv/bin/python -m pytest -q -s tests/test_offline_frames.py
  ```

- Website production build and existing Node test files pass. Optional browser
  acceptance (`web/tests/offline-frames.browser.mjs`) uses explicitly SAMPLE images
  to verify that a loaded image stays visible offline and a new recovered image
  appears after reconnection without duplicates or page errors. Run from `web/`
  after a build, with Playwright installed or `BOB_PLAYWRIGHT_MODULE` pointing to
  its `index.mjs`; the fixture is generated using the repository `.venv`.
- Physical iPhone → Jetson → laptop Wi-Fi-toggle acceptance and any hosted-site
  deployment remain to be performed using the steps above.
