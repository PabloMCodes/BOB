"""Frame pipeline evidence as 4:5 images for the website's skill cards.

uv run python -m tools.web_skill_cards

Presentation only: it crops an already-annotated image and, for the zone card, prints the
verdict the run actually returned along the bottom. It never re-runs or re-judges anything —
the boxes and the reason string come from the evidence directories named below, which are
produced by tools/showcase_stills.py and tools/inspect_zone.py.

The card's own status chip sits over the top-left corner, which is where draw_zone puts its
banner, so the zone verdict is repeated on a bottom strip where nothing covers it.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

CARD_ASPECT = 4 / 5          # w/h, matching aspect-[4/5] on the card frame
LONG_EDGE = 1280
WEB = Path("web/public/media/skills")


def crop_to_aspect(image: np.ndarray, aspect: float, x_bias: float = 0.5, y_bias: float = 0.5) -> np.ndarray:
    """Largest centre-weighted crop with the given w/h aspect; bias 0..1 picks which part to keep."""
    h, w = image.shape[:2]
    if w / h > aspect:
        new_w = int(round(h * aspect))
        x = int(round((w - new_w) * x_bias))
        return image[:, x:x + new_w]
    new_h = int(round(w / aspect))
    y = int(round((h - new_h) * y_bias))
    return image[y:y + new_h, :]


def caption(image: np.ndarray, lines: list[str]) -> np.ndarray:
    """Dark strip across the bottom carrying the verdict verbatim."""
    h, w = image.shape[:2]
    scale = w / 900
    font, thickness = cv2.FONT_HERSHEY_SIMPLEX, max(1, int(round(2 * scale)))
    pad, step = int(18 * scale), int(30 * scale)
    strip = pad * 2 + step * len(lines)
    out = image.copy()
    panel = out[h - strip:h].astype(np.float32) * 0.25
    out[h - strip:h] = panel.astype(np.uint8)
    for i, line in enumerate(lines):
        y = h - strip + pad + step * (i + 1) - int(8 * scale)
        cv2.putText(out, line, (pad, y), font, 0.62 * scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return out


def resize(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    s = min(1.0, LONG_EDGE / max(h, w))
    if s == 1.0:
        return image
    return cv2.resize(image, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def write(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 82]):
        raise OSError(f"Could not write {path}")
    print(f"{path.name:44s} {image.shape[1]}x{image.shape[0]:<5} {path.stat().st_size // 1024} KB")


def main() -> None:
    WEB.mkdir(parents=True, exist_ok=True)

    # Eyewear: head_crop evidence. The crop keeps the three workers, not the sky or the roadway.
    eyewear = Path("runs/showcase/web-eyewear")
    for name, src in (("eyewear-drill-crew.jpg", eyewear / "source/008.jpg"),
                      ("eyewear-drill-crew-detections.jpg", eyewear / "008/annotated.jpg")):
        write(WEB / name, resize(crop_to_aspect(cv2.imread(str(src)), CARD_ASPECT, y_bias=0.42)))

    # Zone: the refusal is the result, so it has to stay readable on the card.
    zone = Path("runs/showcase/web-zones/147-door-range")
    report = json.loads((zone / "findings.json").read_text())["assessment"]["region"]
    lines = [f"Restricted zone: {report['status'].upper()}",
             report["reason"].replace("_", " "),
             "No person assessed - not an all-clear result"]
    for name, src, label in (("zone-yellow-floor-tape.jpg", zone.parent / "source/147.jpg", None),
                             ("zone-yellow-floor-tape-detections.jpg", zone / "annotated.jpg", lines)):
        image = cv2.imread(str(src))
        # draw_zone's banner is top-left, under the card's status chip and repeated below. Both
        # images lose the same top strip so the clean and annotated pair stay in register.
        image = image[int(image.shape[0] * 0.06):]
        framed = resize(crop_to_aspect(image, CARD_ASPECT, x_bias=0.0))
        write(WEB / name, caption(framed, label) if label else framed)


if __name__ == "__main__":
    main()
