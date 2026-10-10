import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from vision.walkway import WalkwayConfig, WalkwayDefinition, detect_changes, load_reference

W, H = 400, 300
TRAPEZOID = ((.35, .25), (.65, .25), (.8, .95), (.2, .95))  # far edge 0 (top), near edge 2 (bottom)
DECLARED = dict(reference_declared_empty=True, camera_declared_fixed=True, walkway_declared_floor_rectangle=True)
CONFIG = WalkwayConfig()


def define(polygon=TRAPEZOID, entry=2, exit_=0, sha="a" * 64, **kw):
    return WalkwayDefinition(walkway_id="walk-1", reference_sha256=sha, width=W, height=H,
                             polygon=polygon, entry_edge=entry, exit_edge=exit_, **{**DECLARED, **kw})


@pytest.fixture(scope="module")
def floor():
    """Deterministic textured scene: the camera check needs background texture."""
    noise = np.random.default_rng(0).integers(0, 256, (H // 8, W // 8, 3)).astype(np.uint8)
    return cv2.GaussianBlur(cv2.resize(noise, (W, H), interpolation=cv2.INTER_CUBIC), (5, 5), 0)


def shifted(image, dx):
    return cv2.warpAffine(image, np.float32([[1, 0, dx], [0, 1, 0]]), (W, H), borderMode=cv2.BORDER_REFLECT)


def test_definition_geometry_and_mask():
    d = define()
    assert d.polygon_px()[2].tolist() == pytest.approx([320., 285.])
    mask, inner = d.mask(), d.mask(CONFIG.edge_margin_px)
    assert mask[200, 200] == 255 and mask[10, 10] == 0
    assert np.count_nonzero(inner) < np.count_nonzero(mask) and not np.any(inner & ~mask)


@pytest.mark.parametrize("kw", [
    dict(polygon=((.1, .1), (.9, .9), (.9, .1), (.1, .9))),          # self-intersecting
    dict(polygon=((.1, .1), (.9, .1), (.5, .3), (.1, .9))),          # nonconvex
    dict(polygon=((.1, .1), (.9, .1), (.9, .9))),                     # triangle
    dict(polygon=((.1, .1), (.5, .05), (.9, .1), (.9, .9), (.1, .9))),  # pentagon / L-shapes out of scope
    dict(polygon=((-.1, .1), (.9, .1), (.9, .9), (.1, .9))),
    dict(polygon=((.1, .1), (float("nan"), .1), (.9, .9), (.1, .9))),
    dict(entry=2, exit_=1),                                           # adjacent edges
    dict(entry=0, exit_=0),
    dict(entry=4, exit_=2),
    dict(reference_declared_empty=False),
    dict(camera_declared_fixed=False),
    dict(walkway_declared_floor_rectangle=False),
    dict(sha="A" * 64),
])
def test_invalid_definition_rejected(kw):
    with pytest.raises(ValidationError):
        define(**kw)


def test_config_file_matches_documented_defaults():
    path = Path(__file__).parents[1] / "configs" / "walkway.yaml"
    assert WalkwayConfig.model_validate(yaml.safe_load(path.read_text())) == WalkwayConfig()


@pytest.mark.parametrize("kw", [dict(blur_kernel_px=4), dict(morph_kernel_px=2), dict(change_threshold=0),
                                dict(unknown=1), dict(min_clear_width_fraction=1.5)])
def test_invalid_config_rejected(kw):
    with pytest.raises(ValidationError):
        WalkwayConfig(**kw)


def test_unchanged_scene_has_no_change_evidence(floor):
    noisy = np.clip(floor.astype(int) + np.random.default_rng(1).integers(-3, 4, floor.shape), 0, 255)
    for image in (floor.copy(), noisy.astype(np.uint8)):
        obs = detect_changes(floor, image, define(), CONFIG)
        assert obs.check.status == "valid" and obs.changed_fraction == 0
        assert not obs.changed.any()


def test_object_inside_walkway_is_changed_only_inside(floor):
    image = floor.copy()
    cv2.rectangle(image, (170, 180), (230, 240), (20, 20, 200), -1)
    obs = detect_changes(floor, image, define(), CONFIG)
    assert obs.check.status == "valid"
    box = np.zeros((H, W), bool)
    box[180:241, 170:231] = True
    assert np.count_nonzero(obs.changed[box]) / box.sum() > .9
    assert not np.any(obs.changed & ~obs.interior)
    assert 0 < obs.changed_fraction < .25


def test_object_outside_walkway_gives_no_walkway_change(floor):
    image = floor.copy()
    cv2.rectangle(image, (10, 200), (60, 260), (20, 20, 200), -1)
    obs = detect_changes(floor, image, define(), CONFIG)
    assert obs.check.status == "valid" and obs.changed_fraction == 0


def test_speck_below_min_area_is_ignored(floor):
    image = floor.copy()
    cv2.rectangle(image, (195, 200), (203, 208), (255, 255, 255), -1)
    assert detect_changes(floor, image, define(), CONFIG).changed_fraction == 0


def test_subthreshold_camera_shift_is_measured(floor):
    obs = detect_changes(floor, shifted(floor, 1), define(), CONFIG)
    assert obs.check.status == "valid" and obs.check.camera_shift_px == pytest.approx(1, abs=.1)


@pytest.mark.parametrize("dx", [5, 7])
def test_camera_moved_is_unverified_not_compensated(floor, dx):
    obs = detect_changes(floor, shifted(floor, dx), define(), CONFIG)
    assert (obs.check.status, obs.check.reason) == ("unverified", "camera_moved")
    assert obs.check.camera_shift_px == pytest.approx(dx, abs=.2)
    assert obs.changed is None and obs.changed_fraction is None


@pytest.mark.parametrize("dx", [3, 10, 40])
def test_any_larger_camera_move_never_yields_evidence(floor, dx):
    # Large moves may defeat the shift estimate; the background-change check still catches them.
    obs = detect_changes(floor, shifted(floor, dx), define(), CONFIG)
    assert obs.check.status == "unverified" and obs.changed is None
    assert obs.check.reason in {"camera_moved", "camera_check_failed", "background_changed"}


def test_lighting_change_is_unverified(floor):
    obs = detect_changes(floor, np.clip(floor.astype(int) + 40, 0, 255).astype(np.uint8), define(), CONFIG)
    assert obs.check.reason == "lighting_changed" and obs.changed is None


def test_background_change_is_unverified(floor):
    image = floor.copy()
    image[:, :120] = 255 - image[:, :120]
    obs = detect_changes(floor, image, define(), CONFIG)
    assert obs.check.reason == "background_changed" and obs.check.background_change_fraction > .2


def test_textureless_scene_cannot_verify_camera():
    flat = np.full((H, W, 3), 128, np.uint8)
    assert detect_changes(flat, flat.copy(), define(), CONFIG).check.reason == "camera_check_failed"


def test_walkway_covering_frame_has_no_background_check(floor):
    d = define(polygon=((0, 0), (1, 0), (1, 1), (0, 1)))
    assert detect_changes(floor, floor.copy(), d, CONFIG).check.reason == "insufficient_background_for_camera_check"


def test_walkway_smaller_than_edge_margin_is_unverified(floor):
    d = define(polygon=((.5, .5), (.52, .5), (.52, .52), (.5, .52)))
    obs = detect_changes(floor, floor.copy(), d, CONFIG)
    assert obs.check.reason == "walkway_too_small" and obs.changed is None


def test_size_mismatch_is_unverified(floor):
    big = cv2.resize(floor, (W * 2, H * 2))
    assert detect_changes(floor, big, define(), CONFIG).check.reason == "image_size_mismatch"


@pytest.mark.parametrize("bad", [np.zeros((H, W), np.uint8), np.zeros((H, W, 3), np.float32)])
def test_non_bgr_input_rejected(floor, bad):
    with pytest.raises(ValueError):
        detect_changes(floor, bad, define(), CONFIG)


def test_reference_is_bound_to_exact_file(floor, tmp_path):
    ref = tmp_path / "empty.png"
    cv2.imwrite(str(ref), floor)
    d = define(sha=hashlib.sha256(ref.read_bytes()).hexdigest())
    assert np.array_equal(load_reference(d, ref), floor)
    other = tmp_path / "other.png"
    cv2.imwrite(str(other), shifted(floor, 1))
    with pytest.raises(ValueError, match="does not match"):
        load_reference(d, other)
