"""Hand review of Roboflow 'boots' boxes: safety boot or not? CLIP sorts them to make it fast.

    # 1. score every boots box once (needs CLIP -> labeling group)
    uv run --group labeling python -m tools.review_boots score
    # 2. review, most work-boot-like first (OpenCV window; resumes where you stopped)
    uv run python -m tools.review_boots review

Keys:  w = safety-boots   s = shoes (fashion / other boot)   a = accept suggestion
       x = drop the whole image (bad / ambiguous label)       b = back   q = save & quit
Every key press is saved to data/labeling/boots_review.json immediately.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import yaml

from vision.config import REPO_ROOT

DATASET = REPO_ROOT / "data" / "external" / "footwear-w1uf6-v2"
SCORES = REPO_ROOT / "data" / "labeling" / "boots_scores.json"
DECISIONS = REPO_ROOT / "data" / "labeling" / "boots_review.json"
# Decisions made by the coding assistant from contact sheets (same written standard, see README).
# The human file always wins where both exist.
ASSISTED = REPO_ROOT / "data" / "labeling" / "boots_review_assisted.json"
SPLITS = ("train", "valid", "test")
CHOICES = {"w": "safety-boots", "s": "shoes", "x": "drop-image"}

WORK_PROMPTS = [
    "a photo of a steel-toe safety work boot",
    "a photo of a construction work boot",
    "a photo of a rugged lace-up leather work boot",
]
OTHER_PROMPTS = [
    "a photo of a fashion boot",
    "a photo of a high-heeled boot",
    "a photo of a knee-high boot",
    "a photo of a sheepskin ugg boot",
    "a photo of a chelsea boot",
    "a photo of a rubber rain boot",
    "a photo of a hiking boot",
]


@dataclass(frozen=True)
class Item:
    key: str                 # "<split>/<stem>#<line index>" — stable id for decisions
    image: Path
    box: tuple[float, float, float, float]  # YOLO normalized cx, cy, w, h


def collect_boots(root: Path = DATASET) -> list[Item]:
    names = yaml.safe_load((root / "data.yaml").read_text())["names"]
    boots_id = names.index("boots")
    items = []
    for split in SPLITS:
        for label in sorted((root / split / "labels").glob("*.txt")):
            image = next((root / split / "images").glob(f"{label.stem}.*"), None)
            if image is None:
                continue
            for i, line in enumerate(label.read_text().splitlines()):
                parts = line.split()
                if parts and int(parts[0]) == boots_id:
                    items.append(Item(f"{split}/{label.stem}#{i}", image, tuple(map(float, parts[1:5]))))
    return items


def crop(item: Item, pad: float = 0.1) -> np.ndarray:
    image = cv2.imread(str(item.image))
    h, w = image.shape[:2]
    cx, cy, bw, bh = item.box
    x1, x2 = int(max(0, (cx - bw * (0.5 + pad)) * w)), int(min(w, (cx + bw * (0.5 + pad)) * w))
    y1, y2 = int(max(0, (cy - bh * (0.5 + pad)) * h)), int(min(h, (cy + bh * (0.5 + pad)) * h))
    return image[y1:max(y2, y1 + 1), x1:max(x2, x1 + 1)]


def clip_scorer(device: str) -> Callable[[list[np.ndarray]], list[float]]:
    """P(work boot) per crop: softmax over work + other prompts, summed over the work ones."""
    import clip  # labeling group
    import torch
    from PIL import Image

    model, preprocess = clip.load("ViT-B/32", device=device)
    with torch.no_grad():
        text = model.encode_text(clip.tokenize(WORK_PROMPTS + OTHER_PROMPTS).to(device))
        text = text / text.norm(dim=-1, keepdim=True)

    def score(crops: list[np.ndarray]) -> list[float]:
        batch = torch.stack([preprocess(Image.fromarray(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))) for c in crops]).to(device)
        with torch.no_grad():
            image = model.encode_image(batch)
            image = image / image.norm(dim=-1, keepdim=True)
            probs = (100.0 * image @ text.T).softmax(dim=-1)
        return probs[:, : len(WORK_PROMPTS)].sum(dim=-1).tolist()

    return score


def score_all(items: list[Item], scorer: Callable[[list[np.ndarray]], list[float]], batch: int = 64) -> dict[str, float]:
    scores = {}
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        for item, s in zip(chunk, scorer([crop(it) for it in chunk])):
            scores[item.key] = round(float(s), 4)
        print(f"scored {min(i + batch, len(items))}/{len(items)}", end="\r")
    print()
    return scores


class Review:
    """Ordered review state; pure (no GUI) so it can be tested."""

    def __init__(self, items: list[Item], scores: dict[str, float], decisions: dict[str, str]) -> None:
        missing = [it.key for it in items if it.key not in scores]
        if missing:
            raise SystemExit(f"{len(missing)} boots boxes have no score — run the `score` command first")
        self.items = sorted(items, key=lambda it: scores[it.key], reverse=True)
        self.scores, self.decisions = scores, dict(decisions)
        self.index = self.next_undecided(0)

    def next_undecided(self, start: int) -> int:
        for i in range(start, len(self.items)):
            if self.items[i].key not in self.decisions:
                return i
        return len(self.items)

    @property
    def done(self) -> bool:
        return self.index >= len(self.items)

    def suggestion(self, item: Item) -> str:
        return "safety-boots" if self.scores[item.key] >= 0.5 else "shoes"

    def apply(self, key: str) -> None:
        if key == "b":
            self.index = max(0, self.index - 1)
            return
        if self.done or key not in (*CHOICES, "a"):
            return
        item = self.items[self.index]
        self.decisions[item.key] = self.suggestion(item) if key == "a" else CHOICES[key]
        self.index = self.next_undecided(self.index + 1)


def render(review: Review) -> np.ndarray:
    item = review.items[review.index]
    patch = crop(item, pad=0.25)
    patch = cv2.resize(patch, (int(patch.shape[1] * 420 / patch.shape[0]), 420))[:, :560]
    context = cv2.imread(str(item.image))
    h, w = context.shape[:2]
    cx, cy, bw, bh = item.box
    cv2.rectangle(context, (int((cx - bw / 2) * w), int((cy - bh / 2) * h)), (int((cx + bw / 2) * w), int((cy + bh / 2) * h)), (0, 255, 0), 3)
    context = cv2.resize(context, (420, 420))
    canvas = np.zeros((500, 1000, 3), np.uint8)
    canvas[60:480, 10:10 + patch.shape[1]] = patch
    canvas[60:480, 570:990] = context
    decided = sum(1 for it in review.items if it.key in review.decisions)
    previous = review.decisions.get(item.key, "-")
    lines = [
        f"{decided}/{len(review.items)} reviewed   work-boot score {review.scores[item.key]:.2f}   suggestion: {review.suggestion(item)}   current: {previous}",
        "w safety-boots   s shoes   a accept suggestion   x drop image   b back   q quit",
    ]
    for i, text in enumerate(lines):
        cv2.putText(canvas, text, (10, 22 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def merged_decisions(user: dict[str, str], assisted: dict[str, str]) -> dict[str, str]:
    """Assistant decisions overlaid by the human's: the human always wins."""
    return {**assisted, **user}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    tmp.replace(path)  # atomic: a crash never leaves a half-written decisions file


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["score", "review", "status"])
    args = parser.parse_args(argv)
    items = collect_boots()

    if args.command == "score":
        from vision.config import resolve_device

        save_json(SCORES, score_all(items, clip_scorer(resolve_device("auto"))))
        print(f"saved {len(items)} scores -> {SCORES.relative_to(REPO_ROOT)}")
        return

    user, assisted = load_json(DECISIONS), load_json(ASSISTED)
    if args.command == "status":
        merged = merged_decisions(user, assisted)
        counts: dict[str, int] = {}
        for value in merged.values():
            counts[value] = counts.get(value, 0) + 1
        print(f"{len(merged)}/{len(items)} decided (you {len(user)}, assistant {len(set(assisted) - set(user))}): {counts}")
        return

    # Only show boxes nobody has decided; assistant calls stay auditable in their own file.
    open_items = [it for it in items if it.key in user or it.key not in assisted]
    review = Review(open_items, load_json(SCORES), user)

    while not review.done:
        cv2.imshow("boots review", render(review))
        key = chr(cv2.waitKey(0) & 0xFF)
        if key == "q":
            break
        review.apply(key)
        save_json(DECISIONS, review.decisions)
    cv2.destroyAllWindows()
    print(f"{len(review.decisions)}/{len(open_items)} of your queue reviewed -> {DECISIONS.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
