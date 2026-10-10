"""Step 2: webcam selection skips black (e.g. idle Continuity Camera) devices. No real camera used."""

import numpy as np
import pytest

from vision.detect import WARMUP_FRAMES, open_camera

BLACK = np.zeros((4, 4, 3), dtype=np.uint8)
LIVE = np.full((4, 4, 3), 90, dtype=np.uint8)


class FakeCapture:
    def __init__(self, frames, opened=True):
        self.frames = list(frames)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return (True, self.frames.pop(0)) if self.frames else (False, None)

    def release(self):
        self.released = True


def _factory(devices):
    caps = {}

    def open_fn(i):
        caps[i] = devices.get(i, FakeCapture([], opened=False))
        return caps[i]

    return open_fn, caps


def test_auto_skips_all_black_camera():
    open_fn, caps = _factory({0: FakeCapture([BLACK] * 50), 1: FakeCapture([BLACK, LIVE])})
    cap, index, frame = open_camera(None, open_fn)
    assert index == 1 and frame.max() > 0
    assert caps[0].released and not caps[1].released


def test_warmup_black_frames_tolerated():
    open_fn, _ = _factory({0: FakeCapture([BLACK] * (WARMUP_FRAMES - 1) + [LIVE])})
    _, index, _ = open_camera(None, open_fn)
    assert index == 0


def test_explicit_black_camera_fails_with_hint():
    open_fn, _ = _factory({0: FakeCapture([BLACK] * 50), 1: FakeCapture([LIVE])})
    with pytest.raises(SystemExit, match=r"\[0\].*black frames.*--camera"):
        open_camera(0, open_fn)


def test_no_camera_mentions_permissions():
    open_fn, _ = _factory({})
    with pytest.raises(SystemExit, match="Privacy & Security"):
        open_camera(None, open_fn)
