"""Operator-authorized steps over advisory camera decisions, without hardware IO.

An empty detection list never grants movement. Every pulse needs a new operator
request while READY. There is no obstacle clearance estimator in this module.
"""
from dataclasses import dataclass
import math

from navigation.preview import Preview, Settings


@dataclass(frozen=True)
class StepSettings:
    seconds: float = 60.
    max_steps: int = 20
    pulse_ms: int = 100
    settle_s: float = 1.

    def __post_init__(self):
        if (type(self.seconds) not in (int, float) or not math.isfinite(self.seconds)
                or not 1 <= self.seconds <= 120):
            raise ValueError("seconds must be finite, in 1..120")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 30:
            raise ValueError("max_steps must be an integer in 1..30")
        if type(self.pulse_ms) is not int or not 100 <= self.pulse_ms <= 150:
            raise ValueError("pulse_ms must be an integer in 100..150")
        if (type(self.settle_s) not in (int, float) or not math.isfinite(self.settle_s)
                or not 1 <= self.settle_s <= 10):
            raise ValueError("settle_s must be finite, in 1..10")


@dataclass(frozen=True)
class StepRequest:
    direction: str
    session_id: str
    event_id: str
    seq_id: int
    deadline: float
    pulse_ms: int


class StepSupervisor:
    def __init__(self, settings=StepSettings(), *, started: float):
        self.settings = settings
        self.started = started
        self.preview = Preview(Settings(stale_s=.5, mission_s=settings.seconds,
                                        cell_m=.25, radius_cells=3))
        self.decision = None
        self.event = self.health = None
        self.wall = self.mono = None
        self.paused = "press R after checking the test area"
        self.fault = None
        self.active = None
        self.attempts = 0
        self.stopped_wall = self.stopped_mono = None
        self.last_clear_key = None
        self.clear_count = 0
        self.clear_since = None

    def pause(self, reason="operator stop"):
        self.paused = reason or "operator stop"
        self.clear_count = 0
        self.clear_since = None

    def fail(self, reason):
        # Exception messages (notably TimeoutError) may be empty. The fault
        # interlock must never depend on a truthy third-party error message.
        self.fault = reason or "unspecified controller failure; restart required"
        self.pause(self.fault)

    def update(self, event, health, wall_ns, mono):
        if (not math.isfinite(mono) or (self.mono is not None and mono < self.mono)
                or (self.wall is not None and wall_ns < self.wall)):
            self.fail("clock regressed; restart required")
        self.event, self.health, self.wall, self.mono = event, health, wall_ns, mono
        self.decision = self.preview.update(event, health, wall_ns, mono)
        d = self.decision
        if d.state in {"STOPPED", "FAULT"}:
            self.pause(d.reason)
        if d.state != "EXPLORE":
            self.clear_count = 0
            self.clear_since = None
        else:
            key = (d.session_id, d.seq_id)
            if key != self.last_clear_key:
                self.last_clear_key = key
                self.clear_count += 1
                if self.clear_since is None:
                    self.clear_since = mono
        return d

    def resume(self):
        # R only releases a host interlock; it never sends ARM or MOTION.
        if self.fault or self.active or not self.decision or self.decision.state != "EXPLORE":
            return False
        self.paused = None
        return True

    def phase(self):
        if self.fault:
            return "FAULT", self.fault
        if self.active:
            return "PULSE", self.active.direction
        if self.mono is None:
            return "WAITING", "waiting for live camera"
        if (self.mono - self.started >= self.settings.seconds
                or self.attempts >= self.settings.max_steps
                or self.decision.state == "COMPLETE"):
            return "COMPLETE", "test limit reached"
        if self.paused:
            return "PAUSED", self.paused
        if self.decision.state != "EXPLORE":
            return self.decision.state, self.decision.reason
        if self.stopped_mono is not None:
            if self.mono - self.stopped_mono < self.settings.settle_s:
                return "SETTLING", "motors stopped; waiting for camera"
            # A frame received AFTER the settling interval, not old inference
            # that completed late. Phone/receiver clocks are never subtracted.
            if self.event.jetson_receive_ts_ns < self.stopped_wall + round(self.settings.settle_s * 1e9):
                return "WAITING", "waiting for a post-settle frame"
        if self.clear_count < 3 or self.mono - self.clear_since < .2:
            return "WAITING", "waiting for three fresh observation frames"
        return "READY", self.decision.suggested_direction

    def request(self):
        if self.phase()[0] != "READY":
            return None  # Never buffer input while blocked, observing or moving.
        d = self.decision
        if d.suggested_direction not in {"forward", "turn_left", "turn_right"}:
            return None
        age = (self.wall - min(self.event.jetson_receive_ts_ns, self.health.emitted_ts_ns)) / 1e9
        deadline = min(self.mono + min(.35, self.preview.settings.stale_s - age),
                       self.started + self.settings.seconds)
        request = StepRequest(d.suggested_direction, d.session_id, str(self.event.event_id),
                              d.seq_id, deadline, self.settings.pulse_ms)
        self.active = request
        self.attempts += 1
        return request

    def allowed(self, request, now):
        return bool(
            self.active is request and not self.fault and not self.paused
            and now < request.deadline and now < self.started + self.settings.seconds
            and self.decision.state == "EXPLORE"
            and self.decision.session_id == request.session_id
            and self.decision.suggested_direction == request.direction
            and self.mono is not None and 0 <= now - self.mono <= .1
        )

    def finished(self, wall_ns, mono):
        self.active = None
        self.stopped_wall, self.stopped_mono = wall_ns, mono
        self.clear_count = 0
        self.clear_since = None
