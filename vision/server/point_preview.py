"""Exact-frame local click preview; optional latest-only worker, no inference IO."""
import base64
import json
from pathlib import Path
import threading
import time

import cv2

from vision.orientation import resolve_orientation
from .slot import LatestSlot


class PointPreviewWriter:
    def __init__(self, directory: Path, run_info: dict, mount: str):
        self.path = directory / 'point_frame.json'
        self.run_info, self.mount = run_info, mount
        self.slot = LatestSlot()
        self.stopped = threading.Event()
        self.last_submit = -float('inf')
        self.dropped = self.written = self.errors = 0
        self.thread = threading.Thread(target=self._run, name='point-preview', daemon=True)
        self.thread.start()

    def submit(self, frame, detection):
        now = time.monotonic()
        if now - self.last_submit < .2:
            return
        self.last_submit = now
        self.dropped += self.slot.put((frame.packet, detection))

    def _run(self):
        while not self.stopped.is_set():
            item = self.slot.take(.1)
            if item is None:
                continue
            packet, detection = item
            try:
                image = detection.image
                h, w = image.shape[:2]
                if w > 960:
                    image = cv2.resize(image, (960, round(h*960/w)), interpolation=cv2.INTER_AREA)
                ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if not ok:
                    raise ValueError('JPEG encoding failed')
                data = {'version': 1, 'run_info': self.run_info,
                        'packet': packet.model_dump(mode='json'),
                        'event': detection.event.model_dump(mode='json'),
                        'orientation': resolve_orientation(packet.image.device_orientation, self.mount).value,
                        'jpeg': base64.b64encode(jpeg).decode('ascii')}
                temp = self.path.with_suffix('.tmp')
                temp.write_text(json.dumps(data))
                temp.replace(self.path)
                self.written += 1
            except Exception:
                self.errors += 1  # stale/missing output inhibits the separate driver

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
        return {'written': self.written, 'dropped': self.dropped, 'errors': self.errors,
                'worker_stopped': not self.thread.is_alive()}
