"""Rotate ARKit sensor-oriented images upright.

ARFrame.capturedImage is always in the camera sensor's native orientation, which is upright
when the device is held in UIDeviceOrientation.landscapeLeft (home button / USB-C on the
right). Every other orientation needs a rotation. Flat orientations (face_up / face_down /
unknown) carry no rotation information, so they fall back to the configured mount orientation.

NOTE: this mapping follows Apple's documented sensor orientation; it is verified on a
physical iPhone in Step 4 (upright check per orientation).
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from vision.schema import DeviceOrientation

_ROTATION: dict[DeviceOrientation, Optional[int]] = {
    DeviceOrientation.LANDSCAPE_LEFT: None,
    DeviceOrientation.LANDSCAPE_RIGHT: cv2.ROTATE_180,
    DeviceOrientation.PORTRAIT: cv2.ROTATE_90_CLOCKWISE,
    DeviceOrientation.PORTRAIT_UPSIDE_DOWN: cv2.ROTATE_90_COUNTERCLOCKWISE,
}
UPRIGHT_ORIENTATIONS = tuple(_ROTATION)


def resolve_orientation(
    reported: DeviceOrientation | str, mount_fallback: DeviceOrientation | str
) -> DeviceOrientation:
    """Return the orientation to rotate by: the reported one, or the mount fallback if flat."""
    reported = DeviceOrientation(reported)
    fallback = DeviceOrientation(mount_fallback)
    if fallback not in _ROTATION:
        raise ValueError(
            f"mount_orientation must be one of {[o.value for o in UPRIGHT_ORIENTATIONS]}, "
            f"got {fallback.value!r}"
        )
    return reported if reported in _ROTATION else fallback


def to_upright(
    image: np.ndarray,
    reported: DeviceOrientation | str,
    mount_fallback: DeviceOrientation | str,
) -> np.ndarray:
    """Rotate a sensor-oriented image so people appear upright. Returns a new array."""
    rotation = _ROTATION[resolve_orientation(reported, mount_fallback)]
    return image.copy() if rotation is None else cv2.rotate(image, rotation)
