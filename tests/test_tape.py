import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from vision.tape import TapeConfig, detect_tape

CONFIG = TapeConfig(inside_is_restricted=True, boundary_is_on_floor=True)


def outline():
    image = np.full((400, 600, 3), 70, np.uint8)
    cv2.rectangle(image, (100, 100), (500, 330), (0, 255, 255), 16)
    return image


def test_complete_outline_recognized():
    r=detect_tape(outline(), CONFIG)
    assert r.status == "recognized" and len(r.polygon) >= 4
    assert cv2.pointPolygonTest(np.array(r.polygon,np.float32),(300.,220.),False)>0


def test_perspective_outline():
    image=np.full((400,600,3),70,np.uint8)
    cv2.polylines(image,[np.array([[200,80],[420,110],[520,340],[80,330]])],True,(0,255,255),15)
    assert detect_tape(image,CONFIG).status == "recognized"


@pytest.mark.parametrize("kind", ["gap","hidden","filled","wrong_color","border","empty"])
def test_unusable_boundaries_never_recognized(kind):
    image=outline()
    if kind in {"gap","hidden"}:
        cv2.rectangle(image,(240,70),(300,140),(70,70,70),-1)
    elif kind == "filled":
        cv2.rectangle(image,(90,90),(510,340),(0,255,255),-1)
    elif kind == "wrong_color":
        image=image[:,:,[1,0,2]].copy()
    elif kind == "border":
        image=outline()[:,100:]
    else:
        image[:]=70
    assert detect_tape(image,CONFIG).status == "unverified"


def test_two_outlines_are_ambiguous():
    image=np.full((400,600,3),70,np.uint8)
    for x in (30,330):
        cv2.rectangle(image,(x,80),(x+220,330),(0,255,255),12)
    assert detect_tape(image,CONFIG).reason == "multiple_closed_yellow_regions"


def test_small_black_lettering_keeps_connected_outline():
    image=outline()
    cv2.putText(image,"CAUTION",(180,104),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
    assert detect_tape(image,CONFIG).status == "recognized"


def test_no_last_known_boundary_is_reused():
    assert detect_tape(outline(),CONFIG).status == "recognized"
    assert detect_tape(np.zeros((400,600,3),np.uint8),CONFIG).status == "unverified"


def test_explicit_operator_convention_required():
    with pytest.raises(ValidationError):
        TapeConfig()
    with pytest.raises(ValidationError):
        TapeConfig(inside_is_restricted=True,boundary_is_on_floor=True,hue_min=50,hue_max=20)
