"""Actual pygame loop with fake BLE/feed; no hardware connection or motion."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncio
from dataclasses import replace
import random
import time
from types import SimpleNamespace
import pygame
import bleak
import hardware.esp32.wander as demo

packets = []
class Client:
    is_connected = True
    services = SimpleNamespace(get_characteristic=lambda uuid: None)
    def __init__(self, device): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def write_gatt_char(self, uuid, packet, response): packets.append(packet)
async def discover(*args, **kwargs): return SimpleNamespace(name='BOB-MotorTest')
bleak.BleakClient = Client
bleak.BleakScanner.find_device_by_filter = discover
feed = SimpleNamespace(current=None, error='')
async def poll(): await asyncio.Future()
feed.poll = poll
demo.HubFeed = lambda url: feed
original = demo.Wander
demo.Wander = lambda: original(random.Random(1))
steps = iter([
    (pygame.KEYDOWN, pygame.K_r, False),
    (None, None, True),
    (pygame.KEYDOWN, pygame.K_r, True),
    (None, None, False),
    (pygame.KEYDOWN, pygame.K_r, False),
    (pygame.WINDOWFOCUSLOST, None, False),
    (pygame.WINDOWFOCUSGAINED, None, False),
    (pygame.QUIT, None, False),
])
seq = 0
def events():
    global seq
    kind, key, person = next(steps)
    seq += 1
    feed.current = demo.Observation(('edge', 'epoch', 'run', 'session'), str(seq),
                                    person, time.monotonic() + 1, 'unverified')
    return [] if kind is None else [pygame.event.Event(kind, **({'key': key} if key else {}))]
pygame.event.get = events
asyncio.run(demo.run('http://127.0.0.1:8780'))
assert packets[:2] == [b'S', b'3']
assert len(packets) == 7, packets
assert packets[2] in [b'F', b'L', b'R'] and packets[4] in [b'F', b'L', b'R']
assert packets[3] == packets[5] == packets[6] == b'S'
print('PASS: start, person stop, no auto-resume, restart, focus loss and exit')
