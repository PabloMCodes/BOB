"""Step 3: PPE pairing rules on hand-built boxes (no model)."""

import pytest

from vision.config import load_config
from vision.ppe import Rule, Verdict, apply_rule, apply_rules, rules_from_config, split_active
from vision.schema import Box

CONFIG = load_config()
RULES = {r.name: r for r in rules_from_config(CONFIG) if isinstance(r, Rule)}
GLASSES, HELMET = RULES["glasses"], RULES["helmet"]

FACE = (100.0, 100.0, 160.0, 180.0)   # 60 x 80 px face
EYES = (108.0, 118.0, 152.0, 136.0)   # centre y=127 -> 0.34 of face height: inside eye band
MOUTH = (115.0, 160.0, 145.0, 172.0)  # centre y=166 -> 0.83: below eye band
HEAD = (95.0, 70.0, 165.0, 180.0)
HELMET_ON = (90.0, 55.0, 170.0, 110.0)


def box(name, xyxy, conf=0.9):
    return Box(source="model", cls_id=0, cls_name=name, conf=conf, xyxy=xyxy)


def only(verdicts):
    assert len(verdicts) == 1
    return verdicts[0]


def test_glasses_in_eye_band_is_wearing():
    v = only(apply_rule(GLASSES, [box("face", FACE), box("glasses", EYES)]))
    assert v.verdict is Verdict.WEARING and v.ppe.xyxy == EYES and v.violation is None


def test_no_glasses_is_violation_on_eye_band():
    v = only(apply_rule(GLASSES, [box("face", FACE, conf=0.8)]))
    assert v.verdict is Verdict.NOT_WEARING
    b = v.violation
    assert b.source == "derived" and b.cls_id is None and b.cls_name == "no-safety-glasses"
    assert b.conf == 0.8  # inherits the face's confidence
    assert b.xyxy == pytest.approx((100.0, 108.0, 160.0, 148.0))  # face band 0.10-0.60


def test_glasses_outside_eye_band_does_not_count():
    assert only(apply_rule(GLASSES, [box("face", FACE), box("glasses", MOUTH)])).verdict is Verdict.NOT_WEARING


def test_glasses_mostly_outside_face_does_not_count():
    # Centre inside the band, but most of the box hangs outside the face.
    wide = (40.0, 118.0, 200.0, 136.0)
    assert only(apply_rule(GLASSES, [box("face", FACE), box("glasses", wide)])).verdict is Verdict.NOT_WEARING


@pytest.mark.parametrize(
    "face, conf",
    [((100.0, 100.0, 120.0, 120.0), 0.9),  # 20 px tall: below min_subject_px
     (FACE, 0.3)],                          # low confidence
)
def test_small_or_uncertain_face_is_unverified_without_box(face, conf):
    v = only(apply_rule(GLASSES, [box("face", face, conf=conf)]))
    assert v.verdict is Verdict.UNVERIFIED and v.violation is None


def test_head_without_face_gives_no_glasses_verdict():
    assert apply_rule(GLASSES, [box("head", HEAD)]) == []


def test_one_glasses_box_cannot_serve_two_faces():
    face_b = (130.0, 100.0, 190.0, 180.0)  # overlaps FACE; both bands contain EYES' centre
    verdicts = apply_rule(GLASSES, [box("face", FACE, 0.9), box("face", face_b, 0.8), box("glasses", EYES)])
    assert sorted(v.verdict for v in verdicts) == [Verdict.NOT_WEARING, Verdict.WEARING]
    assert next(v for v in verdicts if v.verdict is Verdict.WEARING).subject.conf == 0.9


def test_two_people_judged_independently():
    face_b = (300.0, 100.0, 360.0, 180.0)
    verdicts = apply_rule(GLASSES, [box("face", FACE), box("glasses", EYES), box("face", face_b)])
    assert {v.subject.xyxy: v.verdict for v in verdicts} == {FACE: Verdict.WEARING, face_b: Verdict.NOT_WEARING}


def test_helmet_above_head_is_wearing():
    assert only(apply_rule(HELMET, [box("head", HEAD), box("helmet", HELMET_ON)])).verdict is Verdict.WEARING


def test_missing_helmet_violation_is_top_of_head():
    v = only(apply_rule(HELMET, [box("head", HEAD)]))
    assert v.verdict is Verdict.NOT_WEARING
    assert v.violation.xyxy == pytest.approx((95.0, 70.0, 165.0, 136.0))  # clipped to head, band to 0.60


def test_class_names_are_normalized():
    v = only(apply_rule(GLASSES, [box("Face", FACE), box("GLASSES", EYES)]))
    assert v.verdict is Verdict.WEARING


def test_apply_rules_combines_rules():
    derived, verdicts = apply_rules(RULES.values(), [box("face", FACE), box("head", HEAD)])
    assert {b.cls_name for b in derived} == {"no-safety-glasses", "no-helmet"}
    assert len(verdicts) == 2


@pytest.mark.parametrize("region", [[0.6, 0.1], [-0.5, -0.1], [1.0, 1.5]])
def test_invalid_region_rejected(region):
    cfg = dict(CONFIG["ppe"]["rules"]["glasses"], region=region)
    with pytest.raises(ValueError, match="region"):
        Rule.from_config("bad", cfg)


# --- gloves (pair rule on hands) and boots (class rule) ------------------------------------

GLOVES = RULES["gloves"]
BOOTS = next(r for r in rules_from_config(CONFIG) if r.name == "boots")
HAND = (300.0, 400.0, 330.0, 440.0)  # 30 x 40 px


def test_bare_hand_is_no_gloves_on_hand():
    v = only(apply_rule(GLOVES, [box("hands", HAND)]))
    assert v.verdict is Verdict.NOT_WEARING
    assert v.violation.cls_name == "no-gloves" and v.violation.xyxy == pytest.approx(HAND)


def test_gloved_hand_is_wearing_even_if_glove_box_is_larger():
    glove = (295.0, 395.0, 338.0, 448.0)
    assert only(apply_rule(GLOVES, [box("hands", HAND), box("gloves", glove)])).verdict is Verdict.WEARING


def test_each_hand_judged_separately():
    other = (500.0, 400.0, 530.0, 440.0)
    verdicts = apply_rule(GLOVES, [box("hands", HAND), box("hands", other), box("gloves", HAND)])
    assert sorted(v.verdict for v in verdicts) == [Verdict.NOT_WEARING, Verdict.WEARING]


@pytest.mark.parametrize("name, verdict", [("safety-boots", Verdict.WEARING), ("shoes", Verdict.NOT_WEARING)])
def test_boots_class_rule(name, verdict):
    v = only(apply_rule(BOOTS, [box(name, (10.0, 500.0, 60.0, 530.0))]))
    assert v.verdict is verdict
    if verdict is Verdict.NOT_WEARING:
        assert v.violation.cls_name == "no-safety-boots" and v.violation.source == "derived"


def test_tiny_footwear_unverified():
    assert only(apply_rule(BOOTS, [box("shoes", (10.0, 500.0, 30.0, 508.0))])).verdict is Verdict.UNVERIFIED


SH17_NAMES = ["person", "ear", "ear-mufs", "face", "face-guard", "face-mask", "foot", "tool", "glasses",
              "gloves", "helmet", "hands", "head", "medical-suit", "shoes", "safety-suit", "safety-vest"]


def test_boots_inactive_with_sh17_never_approximated():
    active, inactive = split_active(rules_from_config(CONFIG), SH17_NAMES)
    assert [r.name for r in inactive] == ["boots"]
    assert {r.name for r in active} == {"glasses", "helmet", "gloves", "vest"}


def test_boots_active_with_finetuned_classes():
    # The 9 fine-tune classes have no safety-vest, so the vest rule switches off with that model.
    active, inactive = split_active(rules_from_config(CONFIG), CONFIG["training"]["classes"])
    assert [r.name for r in inactive] == ["vest"] and "boots" in {r.name for r in active}


# --- vest (pair rule on the person's torso) -----------------------------------------------

VEST = RULES["vest"]
PERSON = (200.0, 100.0, 300.0, 400.0)  # 100 x 300 px; torso band 0.15-0.65 -> y 145-295
VEST_ON = (210.0, 150.0, 290.0, 280.0)  # centre y=215 -> 0.38


def test_vest_on_torso_is_wearing():
    v = only(apply_rule(VEST, [box("person", PERSON), box("safety-vest", VEST_ON)]))
    assert v.verdict is Verdict.WEARING and v.ppe.xyxy == VEST_ON


def test_no_vest_is_violation_on_torso():
    v = only(apply_rule(VEST, [box("person", PERSON, conf=0.7)]))
    assert v.verdict is Verdict.NOT_WEARING
    b = v.violation
    assert b.source == "derived" and b.cls_name == "no-safety-vest" and b.conf == 0.7
    assert b.xyxy == pytest.approx((200.0, 145.0, 300.0, 295.0))


def test_vest_at_feet_does_not_count():
    # e.g. a vest lying on the floor next to the person's feet
    assert only(apply_rule(VEST, [box("person", PERSON), box("safety-vest", (210.0, 360.0, 290.0, 400.0))])).verdict \
        is Verdict.NOT_WEARING


def test_one_vest_cannot_serve_two_people():
    other = (260.0, 100.0, 360.0, 400.0)  # overlapping person whose torso band also holds the vest
    verdicts = apply_rule(VEST, [box("person", PERSON), box("person", other, conf=0.8), box("safety-vest", VEST_ON)])
    assert sorted(v.verdict for v in verdicts) == [Verdict.NOT_WEARING, Verdict.WEARING]


@pytest.mark.parametrize("person, conf", [((200.0, 100.0, 240.0, 180.0), 0.9), (PERSON, 0.3)])
def test_small_or_uncertain_person_unverified_for_vest(person, conf):
    v = only(apply_rule(VEST, [box("person", person, conf=conf)]))
    assert v.verdict is Verdict.UNVERIFIED and v.violation is None


def test_unknown_rule_kind_rejected():
    config = {"ppe": {"rules": {"x": {"kind": "magic"}}}}
    with pytest.raises(ValueError, match="kind"):
        rules_from_config(config)
