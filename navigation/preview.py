"""Pure navigation preview over admitted C2/C3 observations.

The visited grid records camera positions, not surveyed free space. Directions
are hypothetical and never encode motor commands. All timers use the consumer's
monotonic clock; C2/C3 freshness compares receiver wall timestamps on the SAME host.
"""
from dataclasses import dataclass
import math

from vision.schema import Box, DetectionEvent, StreamHealth, TrackingState


PPE_CLASSES = frozenset({
    "no-helmet", "no-safety-vest", "no-gloves", "no-safety-boots", "no-safety-glasses",
})


@dataclass(frozen=True)
class Settings:
    stale_s: float = 0.75
    observe_s: float = 2.0
    hold_s: float = 10.0
    clear_s: float = 1.0
    cooldown_s: float = 30.0
    confirm_frames: int = 3
    confirm_s: float = 0.4
    cell_m: float = 0.5
    radius_cells: int = 4
    mission_s: float = 120.0

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if type(self.confirm_frames) is not int or self.confirm_frames < 2:
            raise ValueError("confirm_frames must be an integer >= 2")
        if type(self.radius_cells) is not int or not 1 <= self.radius_cells <= 20:
            raise ValueError("radius_cells must be an integer in 1..20")
        if self.confirm_s > self.observe_s:
            raise ValueError("confirmation must fit within the observation window")


@dataclass(frozen=True)
class Decision:
    state: str
    reason: str
    session_id: str | None = None
    seq_id: int | None = None
    camera_cell: tuple[int, int] | None = None
    visited_cells: int = 0
    goal_cell: tuple[int, int] | None = None
    suggested_direction: str = "stop"
    confirmed_ppe: tuple[str, ...] = ()
    announcement: str | None = None
    mode: str = "PREVIEW"
    motor_output_enabled: bool = False


def iou(a: Box, b: Box) -> float:
    ax, ay, bx, by = a.xyxy
    cx, cy, dx, dy = b.xyxy
    intersection = max(0, min(bx, dx) - max(ax, cx)) * max(0, min(by, dy) - max(ay, cy))
    return intersection / ((bx - ax) * (by - ay) + (dx - cx) * (dy - cy) - intersection)


class Preview:
    def __init__(self, settings: Settings = Settings()):
        self.settings = settings
        self.session = None
        self.retired: set[str] = set()
        self.origin = None
        self.visits: dict[tuple[int, int], int] = {}
        self.cell = None
        self.last_key = None
        self.last_phone_ts = self.last_rx = -1
        self.last_mono = None
        self.last_event_mono = None
        self.started = None
        self.halted = False
        self.last_announced = -math.inf  # Global cooldown: no worker identity claim.
        self._reset_inspection()

    def _reset_inspection(self):
        self.person_since = self.hold_until = self.clear_since = None
        self.subject = None
        self.evidence: dict[str, tuple[int, float]] = {}
        self.confirmed: tuple[str, ...] = ()

    def _decision(self, state, reason, event=None, **kwargs):
        return Decision(state, reason, self.session,
                        event.seq_id if event else None, self.cell, len(self.visits),
                        confirmed_ppe=self.confirmed, **kwargs)

    def _stop(self, reason, event=None):
        self._reset_inspection()
        return self._decision("STOPPED", reason, event)

    def update(self, event: DetectionEvent | None, health: StreamHealth | None,
               wall_ns: int, mono: float) -> Decision:
        if not math.isfinite(mono) or (self.last_mono is not None and mono < self.last_mono):
            self.halted = True
        self.last_mono = mono
        if self.halted:
            return self._decision("FAULT", "restart_preview_required", event)
        if event is None or health is None:
            return self._stop("waiting_for_detection_and_health")
        s = self.settings
        # A health session change invalidates the old coordinate map immediately,
        # even if the detector is still finishing a frame from the old session.
        session = str(health.session_id) if health.session_id else None
        if session != self.session:
            changed = self.session is not None
            if self.session:
                self.retired.add(self.session)
            if session in self.retired or len(self.retired) > 32:
                self.halted = True
                return self._stop("retired_session_or_session_limit", event)
            self.session = session
            self.origin = self.cell = self.last_key = None
            self.last_phone_ts = self.last_rx = -1
            self.last_event_mono = None
            self.visits.clear()
            self._reset_inspection()
            if changed:
                return self._stop("session_changed_map_cleared", event)
        for timestamp in (event.jetson_receive_ts_ns, health.emitted_ts_ns):
            age = (wall_ns - timestamp) / 1e9
            if not 0 <= age <= s.stale_s:
                return self._stop("stale_or_future_receiver_timestamp", event)
        if health.stale:
            return self._stop("stream_stale", event)
        if not session or str(event.session_id) != session:
            return self._stop("session_mismatch", event)
        if (not event.pose_valid or event.pose is None
                or event.tracking_state != TrackingState.NORMAL
                or health.tracking_state != TrackingState.NORMAL):
            return self._stop("pose_or_tracking_invalid", event)
        key = (session, event.seq_id)
        fresh = key != self.last_key
        if fresh:
            if (self.last_key and event.seq_id <= self.last_key[1]
                    or event.iphone_frame_ts_ns <= self.last_phone_ts
                    or event.jetson_receive_ts_ns < self.last_rx):
                return self._stop("reordered_observation", event)
            if self.last_event_mono is not None and mono - self.last_event_mono > s.stale_s:
                self._reset_inspection()
            self.last_event_mono = mono
            self.last_key = key
            self.last_phone_ts = event.iphone_frame_ts_ns
            self.last_rx = event.jetson_receive_ts_ns
        pose = event.pose
        if self.origin is None:
            self.origin = (pose.x_m, pose.z_m)
        if self.started is None:
            self.started = mono
        if mono - self.started >= s.mission_s:
            return self._decision("COMPLETE", "preview_time_limit", event)
        dx, dz = pose.x_m - self.origin[0], pose.z_m - self.origin[1]
        cell = (math.floor(dx / s.cell_m + 0.5), math.floor(dz / s.cell_m + 0.5))
        if max(abs(dx), abs(dz)) > s.radius_cells * s.cell_m:
            return self._stop("outside_preview_bounds", event)
        if fresh and cell != self.cell:
            self.visits[cell] = self.visits.get(cell, 0) + 1
            self.cell = cell
        people = [b for b in event.boxes if b.source == "model"
                  and b.cls_name == "person" and b.conf >= 0.5]
        person_seen = bool(people) or any(
            b.source == "model" and b.cls_name in {"head", "face"} and b.conf >= 0.5
            for b in event.boxes)
        if person_seen and self.person_since is None:
            self.person_since = mono
        if self.person_since is not None:
            if person_seen:
                self.clear_since = None
            elif self.clear_since is None:
                self.clear_since = mono
            if self.hold_until is None:
                if fresh:
                    self._observe(event, people, mono)
                if self.confirmed:
                    self.hold_until = mono + s.hold_s
                    if mono - self.last_announced >= s.cooldown_s:
                        self.last_announced = mono
                        return self._decision("ANNOUNCE", "repeated_derived_ppe_evidence", event,
                                              announcement="Missing PPE")
                elif mono - self.person_since >= s.observe_s:
                    self.hold_until = mono + s.hold_s
                else:
                    return self._decision("OBSERVE", "person_observation_unverified", event)
            if mono < self.hold_until:
                return self._decision("HOLD", "ten_second_inspection_pause", event)
            if person_seen or self.clear_since is None or mono - self.clear_since < s.clear_s:
                return self._decision("HOLD", "person_present_or_clear_interval_pending", event)
            self._reset_inspection()
        return self._explore(event)

    def _observe(self, event, people, mono):
        # Only one continuously overlapping person is eligible for speech. This
        # is short-term image association, not persistent identity/tracking.
        if len(people) != 1:
            self.subject = None
            self.evidence.clear()
            return
        person = people[0]
        if self.subject is None or iou(self.subject, person) < 0.3:
            self.evidence.clear()
        self.subject = person
        x1, y1, x2, y2 = person.xyxy
        classes = set()
        for b in event.boxes:
            cx, cy = (b.xyxy[0] + b.xyxy[2]) / 2, (b.xyxy[1] + b.xyxy[3]) / 2
            if (b.source == "derived" and b.cls_name in PPE_CLASSES and b.conf >= 0.5
                    and x1 <= cx <= x2 and y1 <= cy <= y2):
                classes.add(b.cls_name)
        self.evidence = {name: (self.evidence.get(name, (0, mono))[0] + 1,
                                self.evidence.get(name, (0, mono))[1]) for name in classes}
        self.confirmed = tuple(sorted(name for name, (count, start) in self.evidence.items()
                                      if count >= self.settings.confirm_frames
                                      and mono - start >= self.settings.confirm_s))

    def _explore(self, event):
        s = self.settings
        if len(self.visits) == (s.radius_cells * 2 + 1) ** 2:
            return self._decision("COMPLETE", "all_preview_cells_visited", event)
        pose = event.pose
        candidates = []
        for dx, dz in ((0, -1), (-1, 0), (0, 1), (1, 0)):
            x, z = self.cell[0] + dx, self.cell[1] + dz
            if max(abs(x), abs(z)) > s.radius_cells:
                continue
            tx, tz = self.origin[0] + x * s.cell_m, self.origin[1] + z * s.cell_m
            desired = math.atan2(-(tx - pose.x_m), -(tz - pose.z_m))
            delta = (desired - pose.yaw_rad + math.pi) % (2 * math.pi) - math.pi
            candidates.append((self.visits.get((x, z), 0), abs(delta), x, z, delta))
        _, _, x, z, delta = min(candidates)
        direction = "forward" if abs(delta) < 0.3 else ("turn_left" if delta > 0 else "turn_right")
        return self._decision("EXPLORE", "hypothetical_goal_floor_clearance_unknown", event,
                              goal_cell=(x, z), suggested_direction=direction)
