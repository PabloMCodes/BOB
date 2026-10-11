"""Fault-injection tests of the simulated contract, not ESP32 acceptance."""
from dataclasses import replace

import pytest

from hardware.control_sim import MotionRequest, SimulatedController


@pytest.fixture
def rig():
    now = [10.0]
    controller = SimulatedController(lambda: now[0])
    session = controller.connect()
    controller.arm()
    request = MotionRequest(session, 0, now[0], .3, .1, .2)
    return now, controller, request


def assert_stopped(controller):
    status = controller.status()
    assert not status.armed
    assert status.requested_linear_mps == status.requested_angular_radps == 0
    assert status.measured_wheel_velocity is None


def test_missing_producer_expires_at_boundary_and_latches(rig):
    now, c, r = rig
    assert c.send(r)
    now[0] = 10.299
    assert c.status().requested_linear_mps == .1
    now[0] = 10.3
    assert_stopped(c)
    assert c.status().fault == "command_expired"
    assert not c.send(replace(r, sequence=1, issued_at=now[0]))
    assert_stopped(c)


def test_delayed_delivery_does_not_extend_lifetime(rig):
    now, c, r = rig
    now[0] += .2
    assert c.send(r)
    now[0] = 10.3
    assert_stopped(c)


@pytest.mark.parametrize("operation", ["stop", "disconnect"])
def test_stop_and_disconnect_neutralize_and_disarm(rig, operation):
    _, c, r = rig
    assert c.send(r)
    getattr(c, operation)()
    assert_stopped(c)
    assert not c.send(replace(r, sequence=1))


def test_reconnection_requires_arm_and_rejects_old_session(rig):
    _, c, r = rig
    assert c.send(r)
    c.disconnect()
    new_session = c.connect()
    assert_stopped(c)
    assert not c.send(replace(r, session=new_session))
    c.arm()
    assert not c.send(r)
    assert_stopped(c)
    c.arm()
    assert c.send(replace(r, session=new_session))


@pytest.mark.parametrize("changes", [
    {"sequence": 0}, {"sequence": -1}, {"sequence": True},
    {"session": 99}, {"linear_mps": float("nan")},
    {"angular_radps": float("inf")}, {"linear_mps": .21},
    {"angular_radps": -.51}, {"issued_at": 11.0},
    {"issued_at": 9.0}, {"valid_for_s": 0.0},
    {"valid_for_s": .51}, {"linear_mps": "0.1"},
])
def test_bad_or_reordered_request_stops_current_motion(rig, changes):
    _, c, r = rig
    assert c.send(r)
    assert not c.send(replace(r, **({"sequence": 1} | changes)))
    assert_stopped(c)


def test_malformed_packet_stops_motion(rig):
    _, c, r = rig
    assert c.send(r)
    assert not c.send(b"F")
    assert_stopped(c)


def test_latest_request_replaces_motion_without_queue(rig):
    now, c, r = rig
    assert c.send(r)
    now[0] += .1
    assert c.send(replace(r, sequence=1, issued_at=now[0], linear_mps=-.1))
    assert c.status().requested_linear_mps == -.1
    now[0] = 10.4
    assert_stopped(c)


def test_cannot_arm_without_connection():
    c = SimulatedController(lambda: 0.0)
    with pytest.raises(RuntimeError):
        c.arm()
    assert_stopped(c)
