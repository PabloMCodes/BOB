"""Opt-in BLE speech adapter. Deliberately has no arm or motion capability."""
import asyncio
import time

from hardware.controller_protocol import (
    COMMAND_UUID, STATUS_UUID, ControllerState, Fault,
    decode_status, encode_stop, encode_tone,
)


class Speaker:
    def __init__(self, client, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.session = None

    @classmethod
    async def connect(cls, name="BOB-ControllerBench"):
        from bleak import BleakClient, BleakScanner
        device = await BleakScanner.find_device_by_name(name, timeout=15)
        if device is None:
            raise RuntimeError(f"{name} not found")
        client = BleakClient(device)
        speaker = cls(client)
        try:
            await asyncio.wait_for(client.connect(), 15)
            await speaker.initialize()
            return speaker
        except BaseException:
            await client.disconnect()
            raise

    async def stop(self):
        await asyncio.wait_for(self.client.write_gatt_char(
            COMMAND_UUID, encode_stop(), response=True), 1)

    async def status(self):
        status = decode_status(await asyncio.wait_for(
            self.client.read_gatt_char(STATUS_UUID), 1))
        if (not status.connected or status.armed or status.left_pwm or status.right_pwm
                or status.state != ControllerState.DISARMED or status.fault != Fault.NONE):
            raise RuntimeError("Speaker requires a connected, stopped, disarmed controller")
        return status

    async def initialize(self):
        await self.stop()
        self.session = (await self.status()).session

    async def announce(self, deadline):
        if self.clock() >= deadline:
            return False
        status = await self.status()
        if status.session != self.session:
            raise RuntimeError("Controller session changed; restart preview")
        remaining = deadline - self.clock()
        if remaining <= 0:
            return False
        await asyncio.wait_for(self.client.write_gatt_char(
            COMMAND_UUID, encode_tone(self.session), response=True), min(remaining, 1))
        return True  # BLE write acknowledged, not proof of audible playback.

    async def close(self):
        try:
            if self.client.is_connected:
                await self.stop()
        finally:
            await self.client.disconnect()
