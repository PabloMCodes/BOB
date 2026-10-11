"""Local hold-to-drive keyboard remote for either existing BOB BLE firmware."""
import asyncio
from contextlib import suppress

from hardware.controller_protocol import (
    COMMAND_UUID, STATUS_UUID, decode_status, encode_arm, encode_motion, encode_stop,
)

TARGETS = {"F": (200, 0), "B": (-200, 0), "L": (0, 500), "R": (0, -500)}


class Remote:
    def __init__(self, client, legacy=False):
        self.client = client
        self.legacy = legacy
        self.moving = False
        self.session = None
        self.sequence = 0

    async def send(self, packet):
        await asyncio.wait_for(
            self.client.write_gatt_char(COMMAND_UUID, packet, response=True), 1.0)

    async def stop(self):
        self.moving = False
        await self.send(b"S" if self.legacy else encode_stop())

    async def move(self, command):
        linear, angular = TARGETS[command]
        if self.legacy:
            await self.send(command.encode("ascii"))
        else:
            if not self.moving:
                status = decode_status(bytes(await asyncio.wait_for(
                    self.client.read_gatt_char(STATUS_UUID), 1.0)))
                self.session = status.session
                self.sequence = 0 if status.last_sequence is None else status.last_sequence + 1
                await self.send(encode_arm(self.session))
            await self.send(encode_motion(self.session, self.sequence, 300, linear, angular))
            self.sequence += 1
        self.moving = True


def direction(held, enabled):
    """Conflicting keys, focus loss and explicit stop all mean stop."""
    return next(iter(held)) if enabled and len(held) == 1 else None


async def run():
    import pygame
    from bleak import BleakClient, BleakScanner

    print("Looking for BOB-ControllerBench or BOB-MotorTest...", flush=True)
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: (ad.local_name or d.name) in {"BOB-ControllerBench", "BOB-MotorTest"},
        timeout=15,
    )
    if device is None:
        raise RuntimeError("BOB not found. Power it on and close other Bluetooth clients.")
    async with BleakClient(device) as client:
        # Both sketches share a service; only ControllerBench has binary status.
        legacy = client.services.get_characteristic(STATUS_UUID) is None
        remote = Remote(client, legacy)
        try:
            await remote.stop()
            if legacy:
                await remote.send(b"3")
            pygame.init()
            screen = pygame.display.set_mode((560, 240))
            pygame.display.set_caption("BOB arrow-key remote")
            font = pygame.font.Font(None, 30)
            held = set()
            blocked = set()
            keys = {pygame.K_UP: "F", pygame.K_DOWN: "B",
                    pygame.K_LEFT: "L", pygame.K_RIGHT: "R",
                    pygame.K_f: "F", pygame.K_b: "B",
                    pygame.K_l: "L", pygame.K_r: "R"}
            focused = True
            stopping = False
            previous = None
            next_send = 0.0
            running = True
            print("Connected. Hold arrows in the remote window. Space = stop; Esc = quit.", flush=True)
            while running and client.is_connected:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.WINDOWFOCUSLOST:
                        focused = False
                        blocked.update(held)
                        held.clear()
                    elif event.type == pygame.WINDOWFOCUSGAINED:
                        focused = True
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            running = False
                        elif event.key in (pygame.K_SPACE, pygame.K_s):
                            stopping = True
                            blocked.update(held)
                            held.clear()
                        elif event.key in keys and focused and not stopping and event.key not in blocked:
                            held.add(event.key)
                    elif event.type == pygame.KEYUP:
                        held.discard(event.key)
                        blocked.discard(event.key)
                        if event.key in (pygame.K_SPACE, pygame.K_s):
                            stopping = False
                # Polling clears keys whose release happened outside the window.
                pressed = pygame.key.get_pressed()
                held = {key for key in held if pressed[key]}
                blocked = {key for key in blocked if pressed[key]}
                command = direction({keys[key] for key in held}, focused and not stopping and running)
                now = asyncio.get_running_loop().time()
                if command is None:
                    if remote.moving:
                        await remote.stop()
                elif command != previous or now >= next_send:
                    await remote.move(command)
                    next_send = now + 0.1
                previous = command
                screen.fill((22, 27, 34))
                lines = ["BOB  |  Bluetooth remote", "Hold arrow keys (or F / B / L / R) to move",
                         "Release = stop    Space = stop    Esc = quit",
                         f"{'MotorTest' if legacy else 'ControllerBench'}: {command or 'STOPPED'}"]
                for i, line in enumerate(lines):
                    screen.blit(font.render(line, True, (230, 235, 240)), (24, 28 + i * 48))
                pygame.display.flip()
                await asyncio.sleep(0.01)
        finally:
            if client.is_connected:
                with suppress(Exception):
                    await remote.stop()
            pygame.quit()


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as error:
        raise SystemExit(f"Remote error: {error}") from error


if __name__ == "__main__":
    main()
