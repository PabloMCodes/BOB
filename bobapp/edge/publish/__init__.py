"""Publication hook: vision.server / tools.replay_detect -> bounded writer -> edge store (plan Step 3).

Layout:
  publisher.py    EdgePublisher — the only entry point CV code calls
  observation.py  observation body (C2 + verdicts + rule availability + C7)
  evidence.py     evidence triggers, per-session rate limit (D6), JPEG + evidence body
  track.py        downsampled valid phone-camera track (plan §7)
  live.py         live snapshot, annotated preview (D5), producer capability list
"""

from .publisher import EdgePublisher

__all__ = ["EdgePublisher"]
