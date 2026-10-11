"""Controller contract experiment. Simulation only: no radio or motor imports.

Run with ``python -m hardware.control_sim``. Times belong to one injected
monotonic clock; this is NOT a wire protocol for unsynchronized devices.
"""
from dataclasses import asdict, dataclass
import json
import math
from typing import Callable, Protocol


@dataclass(frozen=True)
class MotionRequest:
    session: int
    sequence: int
    issued_at: float
    valid_for_s: float
    linear_mps: float
    angular_radps: float


@dataclass(frozen=True)
class Status:
    session: int
    connected: bool
    armed: bool
    last_sequence: int
    requested_linear_mps: float
    requested_angular_radps: float
    fault: str | None
    measured_wheel_velocity: None = None
    mode: str = "SIMULATION"


class ControllerLink(Protocol):
    """Local application boundary; a future hardware adapter needs its own protocol."""

    def send(self, request: MotionRequest) -> bool: ...
    def stop(self) -> None: ...
    def status(self) -> Status: ...


class SimulatedController:
    """Models lease expiry independently of the caller supplying fresh requests.

    Every simulated receive/status read checks the injected clock. There is no
    background task and no claim of physical stopping or real-time execution.
    Limits below are test fixtures, not calibrated rover operating limits.
    """

    MAX_LINEAR = 0.2
    MAX_ANGULAR = 0.5
    MAX_LEASE = 0.5

    def __init__(self, clock: Callable[[], float]):
        self.clock = clock
        self.session = 0
        self.connected = False
        self.armed = False
        self.last_sequence = -1
        self.linear = self.angular = 0.0
        self.deadline = None
        self.fault = None

    def _neutral(self):
        self.linear = self.angular = 0.0
        self.deadline = None

    def _fault(self, reason: str):
        self._neutral()
        self.armed = False
        self.fault = reason

    def connect(self) -> int:
        self._neutral()
        self.session += 1
        self.connected = True
        self.armed = False
        self.last_sequence = -1
        self.fault = None
        return self.session

    def disconnect(self):
        self.connected = False
        self._fault("disconnected")

    def arm(self):
        if not self.connected:
            raise RuntimeError("Cannot arm a disconnected simulator")
        # Explicit operator action, never automatically called by send/reconnect.
        self._neutral()
        self.fault = None
        self.armed = True

    def stop(self):
        self._neutral()
        self.armed = False

    def tick(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            self._fault("command_expired")

    def send(self, request: MotionRequest) -> bool:
        self.tick()
        if not self.connected or not self.armed:
            return False
        if not isinstance(request, MotionRequest):
            self._fault("malformed_request")
            return False
        numeric = (request.issued_at, request.valid_for_s,
                   request.linear_mps, request.angular_radps)
        if (type(request.session) is not int or type(request.sequence) is not int
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in numeric)):
            self._fault("malformed_request")
            return False
        if request.session != self.session or request.sequence <= self.last_sequence:
            self._fault("old_session_or_sequence")
            return False
        if (not 0 < request.valid_for_s <= self.MAX_LEASE
                or abs(request.linear_mps) > self.MAX_LINEAR
                or abs(request.angular_radps) > self.MAX_ANGULAR):
            self._fault("outside_limits")
            return False
        now = self.clock()
        deadline = request.issued_at + request.valid_for_s
        if request.issued_at > now or deadline <= now:
            self._fault("invalid_request_time")
            return False
        self.last_sequence = request.sequence
        self.linear = request.linear_mps
        self.angular = request.angular_radps
        # Receiving a delayed request does not grant it a fresh full lease.
        self.deadline = deadline
        return True

    def status(self) -> Status:
        self.tick()
        return Status(self.session, self.connected, self.armed, self.last_sequence,
                      self.linear, self.angular, self.fault)


def main():
    now = [0.0]
    controller = SimulatedController(lambda: now[0])

    def show(event):
        print(json.dumps({"event": event, "time_s": now[0], **asdict(controller.status())}))

    session = controller.connect()
    show("connected_disarmed")
    controller.arm()
    controller.send(MotionRequest(session, 0, now[0], .3, .1, 0.0))
    show("fresh_request")
    now[0] = .3
    show("producer_stopped_sending_watchdog_expired")
    controller.send(MotionRequest(session, 1, now[0], .3, .1, 0.0))
    show("fresh_request_cannot_clear_fault")
    controller.disconnect()
    session = controller.connect()
    show("reconnected_disarmed")
    controller.arm()
    controller.send(MotionRequest(session, 0, now[0], .3, .1, 0.0))
    controller.stop()
    show("explicit_stop_disarms")


if __name__ == "__main__":
    main()
