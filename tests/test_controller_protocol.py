import struct

import pytest

from hardware.controller_protocol import (
    ControllerState, Fault, PacketType, VERSION, decode_status, encode_arm,
    encode_motion, encode_stop, encode_tone,
)


def test_packets_fit_default_ble_payload_and_have_stable_bytes():
    assert encode_stop() == bytes([VERSION, PacketType.STOP])
    assert encode_arm(0x12345678) == bytes.fromhex("010178563412")
    assert encode_tone(0x12345678) == bytes.fromhex("010378563412")
    packet = encode_motion(0x12345678, 9, 300, -100, 250)
    assert packet == bytes.fromhex("010278563412090000002c019cfffa00")
    assert len(packet) <= 20


@pytest.mark.parametrize("kwargs", [
    {"session": -1}, {"session": True}, {"sequence": -1},
    {"sequence": 0x1_0000_0000}, {"lease_ms": 99}, {"lease_ms": 501},
    {"linear_mmps": -201}, {"linear_mmps": 201},
    {"angular_mradps": -501}, {"angular_mradps": 501},
    {"linear_mmps": 1.5},
])
def test_motion_encoder_rejects_unrepresentable_values(kwargs):
    values = dict(session=1, sequence=0, lease_ms=300,
                  linear_mmps=0, angular_mradps=0)
    values.update(kwargs)
    with pytest.raises(ValueError):
        encode_motion(**values)


def test_decode_status_exposes_unmeasured_encoder_state():
    packet = struct.pack("<BBBBIIhh", VERSION, ControllerState.MOVING,
                         Fault.NONE, 0b0111, 42, 8, -85, 85)
    status = decode_status(packet)
    assert status.connected and status.armed and status.has_sequence
    assert not status.encoder_feedback
    assert status.session == 42 and status.last_sequence == 8
    assert (status.left_pwm, status.right_pwm) == (-85, 85)


def test_decode_status_without_sequence_uses_none():
    packet = struct.pack("<BBBBIIhh", VERSION, ControllerState.DISARMED,
                         Fault.NONE, 1, 7, 999, 0, 0)
    assert decode_status(packet).last_sequence is None


@pytest.mark.parametrize("packet", [b"", bytes(16), bytes([2]) + bytes(15)])
def test_decode_status_rejects_bad_size_or_version(packet):
    with pytest.raises(ValueError):
        decode_status(packet)


def test_decode_status_rejects_unknown_enum_and_flags():
    base = [VERSION, ControllerState.DISARMED, Fault.NONE, 1, 1, 0, 0, 0]
    for index, value in [(1, 99), (2, 99), (3, 0x80)]:
        row = list(base)
        row[index] = value
        with pytest.raises(ValueError):
            decode_status(struct.pack("<BBBBIIhh", *row))
