"""Wheels-raised BLE client for BOB_ControllerBench firmware.

This tool only sends bounded manual trials. It is not an autonomous navigator.
Run from the repository root with ``python -m hardware.esp32.bob_controller``.
"""
import asyncio
from contextlib import suppress

from bleak import BleakClient, BleakScanner

from hardware.controller_protocol import (
    COMMAND_UUID, STATUS_UUID, ControllerStatus, decode_status, encode_arm,
    encode_motion, encode_stop, encode_tone,
)


DEVICE_NAME = "BOB-ControllerBench"
LEASE_MS = 300
SEND_INTERVAL_S = 0.1
DEFAULT_TRIAL_S = 0.5
MAX_TRIAL_S = 2.0


def describe(status: ControllerStatus) -> str:
    sequence = "none" if status.last_sequence is None else str(status.last_sequence)
    return (f"state={status.state.name} fault={status.fault.name} "
            f"session={status.session:08x} seq={sequence} "
            f"pwm=({status.left_pwm},{status.right_pwm}) "
            f"encoders={'yes' if status.encoder_feedback else 'unavailable'}")


async def read_status(client: BleakClient) -> ControllerStatus:
    return decode_status(bytes(await client.read_gatt_char(STATUS_UUID)))


async def send(client: BleakClient, packet: bytes):
    await client.write_gatt_char(COMMAND_UUID, packet, response=True)


async def bounded_motion(client: BleakClient, linear: int, angular: int,
                         duration: float, sequence: int) -> int:
    if not 0.1 <= duration <= MAX_TRIAL_S:
        raise ValueError(f"duration must be 0.1..{MAX_TRIAL_S:.1f} seconds")
    status = await read_status(client)
    if not status.armed:
        raise RuntimeError("Controller is not armed; enter ARM first")
    session = status.session
    loop = asyncio.get_running_loop()
    end = loop.time() + duration
    try:
        while loop.time() < end:
            await send(client, encode_motion(session, sequence, LEASE_MS,
                                             linear, angular))
            sequence += 1
            await asyncio.sleep(min(SEND_INTERVAL_S, max(0, end - loop.time())))
    finally:
        # STOP is deliberately session-independent and disarms the controller.
        await send(client, encode_stop())
    return sequence


async def main():
    print(f"Looking for {DEVICE_NAME}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15)
    if device is None:
        print("Not found. Upload BOB_ControllerBench and check ESP32 power.")
        return
    async with BleakClient(device) as client:
        status = await read_status(client)
        sequence = 0 if status.last_sequence is None else status.last_sequence + 1
        print("Connected and stopped:", describe(status))
        print("Commands: STATUS, ARM, F/B/L/R [seconds], STOP, TONE, Q")
        print("Motion trials default to 0.5 s and never exceed 2 s.")
        print("Wheels raised: direction trials request the firmware's 85/255 PWM cap.")
        try:
            while client.is_connected:
                parts = (await asyncio.to_thread(input, "BOB> ")).strip().upper().split()
                if not parts:
                    continue
                command = parts[0]
                if command == "Q":
                    break
                if command == "STATUS":
                    print(describe(await read_status(client)))
                    continue
                if command == "STOP":
                    await send(client, encode_stop())
                    print(describe(await read_status(client)))
                    continue
                status = await read_status(client)
                if command == "ARM":
                    await send(client, encode_arm(status.session))
                    print(describe(await read_status(client)))
                    continue
                if command == "TONE":
                    await send(client, encode_tone(status.session))
                    print("Missing PPE speech requested (speech-1 firmware); controller stopped and disarmed.")
                    continue
                if command not in {"F", "B", "L", "R"} or len(parts) > 2:
                    print("Use STATUS, ARM, F/B/L/R [seconds], STOP, TONE, or Q.")
                    continue
                duration = float(parts[1]) if len(parts) == 2 else DEFAULT_TRIAL_S
                # Match speed digit 3 in the working BOB_MotorTest sketch.
                # These are open-loop requests, not measured wheel speeds.
                targets = {"F": (200, 0), "B": (-200, 0),
                           "L": (0, 500), "R": (0, -500)}
                sequence = await bounded_motion(client, *targets[command],
                                                duration, sequence)
                print("Trial ended and controller disarmed:",
                      describe(await read_status(client)))
        finally:
            if client.is_connected:
                with suppress(Exception):
                    await send(client, encode_stop())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    except Exception as error:
        print(f"Controller error: {error}")
