import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sys
sys.path.insert(0, os.getcwd())
import asyncio
from types import SimpleNamespace
import pygame
import bleak
from hardware.esp32.remote import run

packets = []
class Client:
    is_connected = True
    services = SimpleNamespace(get_characteristic=lambda uuid: None)
    def __init__(self, device): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def write_gatt_char(self, uuid, packet, response): packets.append(packet)
async def discover(*args, **kwargs): return object()
bleak.BleakClient = Client
bleak.BleakScanner.find_device_by_filter = discover
steps = iter([
    ([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP)], {pygame.K_UP}),
    ([pygame.event.Event(pygame.KEYUP, key=pygame.K_UP)], set()),
    ([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT)], {pygame.K_LEFT}),
    ([pygame.event.Event(pygame.WINDOWFOCUSLOST)], {pygame.K_LEFT}),
    ([pygame.event.Event(pygame.WINDOWFOCUSGAINED)], {pygame.K_LEFT}),
    ([pygame.event.Event(pygame.KEYUP, key=pygame.K_LEFT)], set()),
    ([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)], {pygame.K_RIGHT}),
    ([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)], {pygame.K_RIGHT, pygame.K_SPACE}),
    ([pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)], {pygame.K_RIGHT}),
    ([pygame.event.Event(pygame.QUIT)], set()),
])
pressed = set()
def events():
    global pressed
    event_list, pressed = next(steps)
    return event_list
class Pressed:
    def __getitem__(self, key): return key in pressed
pygame.event.get = events
pygame.key.get_pressed = lambda: Pressed()
asyncio.run(run())
assert packets == [b'S', b'3', b'F', b'S', b'L', b'S', b'R', b'S', b'S'], packets
print('PASS: window loop release, focus loss, no resume, Space stop and exit')
