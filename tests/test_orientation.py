"""Step 2: sensor-orientation -> upright rotation mapping."""

import numpy as np
import pytest

from vision.config import load_config
from vision.orientation import UPRIGHT_ORIENTATIONS, resolve_orientation, to_upright
from vision.schema import DeviceOrientation as O


def _marked() -> np.ndarray:
    """2x3 sensor image with a unique value in the top-left corner (landscape, W > H)."""
    image = np.zeros((2, 3, 3), dtype=np.uint8)
    image[0, 0] = 255
    return image


def _marker_corner(image: np.ndarray) -> tuple[int, int]:
    ys, xs = np.nonzero(image[:, :, 0])
    return int(ys[0]), int(xs[0])


@pytest.mark.parametrize(
    "orientation, shape, corner",
    [
        (O.LANDSCAPE_LEFT, (2, 3), (0, 0)),       # native sensor orientation: unchanged
        (O.LANDSCAPE_RIGHT, (2, 3), (1, 2)),      # 180°
        (O.PORTRAIT, (3, 2), (0, 1)),             # 90° clockwise
        (O.PORTRAIT_UPSIDE_DOWN, (3, 2), (2, 0)), # 90° counter-clockwise
    ],
)
def test_rotation_mapping(orientation, shape, corner):
    out = to_upright(_marked(), orientation, O.LANDSCAPE_LEFT)
    assert out.shape[:2] == shape
    assert _marker_corner(out) == corner


@pytest.mark.parametrize("flat", [O.FACE_UP, O.FACE_DOWN, O.UNKNOWN])
def test_flat_orientation_uses_mount_fallback(flat):
    assert resolve_orientation(flat, O.PORTRAIT) is O.PORTRAIT
    assert to_upright(_marked(), flat, "portrait").shape[:2] == (3, 2)


def test_reported_orientation_wins_over_fallback():
    assert resolve_orientation("landscape_right", "portrait") is O.LANDSCAPE_RIGHT


@pytest.mark.parametrize("bad", ["face_up", "unknown"])
def test_fallback_must_be_upright_capable(bad):
    with pytest.raises(ValueError, match="mount_orientation"):
        resolve_orientation(O.PORTRAIT, bad)


def test_returns_copy_not_view():
    image = _marked()
    out = to_upright(image, O.LANDSCAPE_LEFT, O.LANDSCAPE_LEFT)
    out[:] = 0
    assert image[0, 0, 0] == 255


def test_default_config_mount_orientation_is_valid():
    assert O(load_config()["camera"]["mount_orientation"]) in UPRIGHT_ORIENTATIONS
