import pytest
from pydantic import ValidationError

from vision.schema import Box, ImageSize
from vision.zones import ImageZone, ZoneRegion, assess_zone

SIZE = ImageSize(width=400, height=400)
REGION = ZoneRegion("test", "recognized", "operator_defined", ((100., 200.), (300., 200.), (300., 350.), (100., 350.)))


def box(name, xyxy, conf=.9):
    return Box(source="model", cls_id=0, cls_name=name, conf=conf, xyxy=xyxy)


PERSON = box("person", (80., 30., 220., 330.))


def test_reference_image_binding():
    zone = ImageZone(zone_id="test", image_sha256="a"*64, width=400, height=400,
                     polygon=((.1,.1),(.9,.1),(.9,.9),(.1,.9)))
    assert zone.region("a"*64, SIZE).status == "recognized"
    assert zone.region("b"*64, SIZE).status == "unverified"
    assert zone.region("a"*64, ImageSize(width=800,height=400)).status == "unverified"


@pytest.mark.parametrize("poly", [((0,0),(1,1),(1,0),(0,1)), ((0,0),(0,0),(0,0)), ((-1,0),(1,0),(1,1)), ((0,0),(float('nan'),1),(1,0))])
def test_invalid_polygon_rejected(poly):
    with pytest.raises(ValidationError):
        ImageZone(zone_id="z", image_sha256="a"*64, width=400,height=400,polygon=poly)


def test_person_bbox_overlap_alone_is_unverified():
    assert assess_zone(REGION,[PERSON],SIZE).people[0].status == "unverified"


@pytest.mark.parametrize("name", ["foot", "shoes", "safety-boots"])
def test_visible_foot_inside_is_only_possible_finding(name):
    result = assess_zone(REGION,[PERSON,box(name,(120.,280.,160.,320.))],SIZE)
    assert result.people[0].status == "possible_person_in_zone"
    assert result.people[0].evidence_box_indices == (1,)


def test_boundary_band_is_unverified():
    assert assess_zone(REGION,[PERSON,box("foot",(80.,280.,120.,320.))],SIZE).people[0].reason == "foot_near_boundary"


def test_outside_evidence_does_not_claim_person_clearance():
    r=assess_zone(REGION,[PERSON,box("foot",(80.,280.,98.,320.))],SIZE)
    assert r.people[0].status == "observed_feet_outside"


@pytest.mark.parametrize("foot", [box("foot",(120.,280.,160.,320.),.2),box("foot",(120.,280.,125.,285.)),box("foot",(120.,200.,160.,399.))])
def test_uncertain_tiny_or_cropped_foot_unverified(foot):
    assert assess_zone(REGION,[PERSON,foot],SIZE).people[0].status == "unverified"


def test_shared_foot_is_not_assigned_to_two_people():
    r=assess_zone(REGION,[PERSON,PERSON,box("foot",(120.,280.,160.,320.))],SIZE)
    assert all(p.status == "unverified" for p in r.people)


def test_invalid_zone_never_makes_a_finding():
    r=assess_zone(ZoneRegion("z","unverified","moved",()),[PERSON,box("foot",(120.,280.,160.,320.))],SIZE)
    assert r.people[0].status == "unverified"


def test_no_person_is_no_assessment():
    assert assess_zone(REGION,[],SIZE).people == ()
