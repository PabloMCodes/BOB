"""Single-pulse BLE executor. No lease refresh, reconnect, planning or CV imports.

The firmware still maps intent units to open-loop PWM. No wheel speed is measured.
The async pulse/stop/announce boundary can be retained with encoder feedback later.
"""
import asyncio
import time
from typing import Protocol

from hardware.controller_protocol import (
    COMMAND_UUID, STATUS_UUID, ControllerState, Fault, decode_status,
    encode_arm, encode_motion, encode_stop, encode_tone,
)


class StepLink(Protocol):
    async def pulse(self, request, allowed, abort) -> bool: ...
    async def stop(self): ...
    async def announce(self, deadline, allowed) -> bool: ...
    async def close(self): ...


class PulseLink:
    def __init__(self, client, clock=time.monotonic):
        self.client, self.clock = client, clock
        self.session = None
        self.sequence = 0
        self.last_status = None

    @classmethod
    async def connect(cls, name="BOB-ControllerBench"):
        from bleak import BleakClient, BleakScanner
        device = await BleakScanner.find_device_by_name(name, timeout=15)
        if device is None:
            raise RuntimeError(f"{name} not found")
        link = cls(BleakClient(device))
        stage = "BLE connection"
        try:
            await asyncio.wait_for(link.client.connect(), 15)
            stage = "startup STOP write"
            await link._write(encode_stop(), timeout=3)
            stage = "startup neutral-status read"
            await link._status(timeout=3)
            return link
        except asyncio.TimeoutError as exc:
            await link.client.disconnect()
            raise RuntimeError(f"{stage} timed out; no ARM command sent") from exc
        except BaseException:
            await link.client.disconnect()
            raise

    async def _write(self, packet, timeout=.3):
        await asyncio.wait_for(self.client.write_gatt_char(COMMAND_UUID, packet, response=True), timeout)

    async def _status(self, armed=False, timeout=.3):
        status = decode_status(await asyncio.wait_for(self.client.read_gatt_char(STATUS_UUID), timeout))
        if (not status.connected or status.fault != Fault.NONE
                or status.armed != armed or status.left_pwm or status.right_pwm
                or status.state != (ControllerState.ARMED if armed else ControllerState.DISARMED)):
            raise RuntimeError("controller did not confirm expected neutral output/state")
        if self.session is None:
            self.session = status.session
            self.sequence = 0 if status.last_sequence is None else status.last_sequence + 1
        if status.session != self.session:
            raise RuntimeError("controller session changed; restart required")
        self.last_status = status
        return status

    async def stop(self):
        await self._write(encode_stop())
        return await self._status()

    async def pulse(self, request, allowed, abort):
        targets = {"forward": (200, 0), "turn_left": (0, 500), "turn_right": (0, -500)}
        if request.direction not in targets or not 100 <= request.pulse_ms <= 150:
            raise ValueError("unsupported step direction or lease")

        def permitted():
            return not abort.is_set() and self.clock() < request.deadline and allowed()

        sent = False
        try:
            if not permitted():
                return False
            await self._status()
            if not permitted():
                return False
            await self._write(encode_arm(self.session))
            await self._status(armed=True)
            if not permitted():
                return False
            sequence = self.sequence
            self.sequence += 1
            start = self.clock()
            # Exactly ONE packet per operator authorization. If this process
            # hangs after delivery, the existing ESP32 lease expires itself.
            await self._write(encode_motion(self.session, sequence, request.pulse_ms,
                                            *targets[request.direction]))
            sent = True
            remaining = max(0, request.pulse_ms / 1000 - (self.clock() - start))
            try:
                await asyncio.wait_for(abort.wait(), remaining)
            except asyncio.TimeoutError:
                pass
        finally:
            status = await self.stop()
        if sent and status.last_sequence != sequence:
            raise RuntimeError("controller did not acknowledge the motion sequence")
        return sent

    async def announce(self, deadline, allowed):
        await self._status()
        if self.clock() >= deadline or not allowed():
            return False
        await self._write(encode_tone(self.session))
        return True

    async def close(self):
        try:
            if self.client.is_connected:
                await self.stop()
        finally:
            await self.client.disconnect()
