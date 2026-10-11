"""Supervised Mac wander demo: existing hub observations -> existing BLE remote."""
import argparse
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
import multiprocessing
import queue
import random
import time
from urllib.request import Request, urlopen

from hardware.controller_protocol import STATUS_UUID
from hardware.esp32.remote import Remote

MAX_AGE_S = 1.0
PULSE_S = 0.25
REST_S = 0.6
MISSION_S = 30.0


@dataclass(frozen=True)
class Observation:
    identity: tuple
    key: str
    person: bool
    expires: float
    ppe: str


def observation(status_data, page_data, started, now):
    """Validate existing C10/C2 contracts; compare clocks only on their own host."""
    from bobapp.hub.api.models.common import Page
    from bobapp.hub.api.models.status import StatusResponse

    status = StatusResponse.model_validate(status_data)
    page = Page.model_validate(page_data)
    live = status.live
    if (status.workspace != 'rover' or page.workspace != 'rover'
            or not status.live_is_current or live is None or live.source_mode != 'LIVE'
            or not live.run_id or live.health is None or live.health.stale):
        raise ValueError('Waiting for live Jetson detections')
    if len(page.items) != 1:
        raise ValueError('Waiting for a realtime observation')
    item = page.items[0]
    record = item.record
    if (item.delivery != 'realtime' or record.source_mode != 'LIVE'
            or record.body.kind != 'observation'
            or (record.edge_id, record.store_epoch, record.run_id)
            != (live.edge_id, live.store_epoch, live.run_id)):
        raise ValueError('History or mismatched vision run')
    event = record.body.event
    if event.session_id != live.health.session_id:
        raise ValueError('Camera session changed')
    hub_age = status.live_received_age_ms
    ages = [live.freshness.video.age_ms, live.freshness.results.age_ms,
            live.freshness.health.age_ms, hub_age]
    if any(age is None or not 0 <= age <= MAX_AGE_S * 1000 for age in ages):
        raise ValueError('Camera feed is stale')
    # Both timestamps below belong to the Jetson, never the Mac or iPhone.
    frame_age = (record.rover.wall_ns - event.jetson_receive_ts_ns) / 1e9
    record_age = (live.rover.mono_ns - record.rover.mono_ns) / 1e9
    if frame_age < 0 or record_age < -MAX_AGE_S:
        raise ValueError('Waiting for matching live status')
    age = max(frame_age + max(0, record_age), max(ages[:3]) / 1000) + hub_age / 1000 + now - started
    if age >= MAX_AGE_S:
        raise ValueError('Jetson observation is too old')
    person = any(box.source == 'model' and box.cls_name in {'person', 'head', 'face'}
                 and box.conf >= 0.5 for box in event.boxes)
    ppe = ', '.join(f'{name}: {verdict.value}' for name, verdict in record.body.frame_verdicts.items())
    return Observation((record.edge_id, str(record.store_epoch), record.run_id,
                        str(event.session_id)), str(event.event_id), person,
                       now + MAX_AGE_S - age, ppe or 'PPE unverified')


class Wander:
    """No camera clearance claim: bounded random bursts in an operator-cleared area."""
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.active = False
        self.reason = 'Press R to start a 30-second search'
        self.identity = None
        self.command = None
        self.until = self.rest_until = self.deadline = 0.0
        self.used_key = None
        self.latest_key = None
        self.key_since = 0.0

    def stop(self, reason):
        self.active = False
        self.command = None
        self.reason = reason

    def update(self, obs, now, *, start=False, stop=False):
        if stop:
            self.stop('Paused — R to restart')
            return None
        if obs is None or now >= obs.expires:
            self.stop('Waiting for fresh Jetson detections — R to restart')
            return None
        if obs.key != self.latest_key:
            self.latest_key, self.key_since = obs.key, now
        elif now - self.key_since >= MAX_AGE_S:
            self.stop('Frozen detection feed — R to restart')
            return None
        if self.identity is not None and obs.identity != self.identity:
            self.identity = obs.identity
            self.stop('Vision run/session changed — R to restart')
            return None
        self.identity = obs.identity
        if obs.person:
            self.stop('PERSON FOUND — stopped for PPE inspection')
            return None
        if start and not self.active:
            self.active = True
            self.deadline = now + MISSION_S
            self.rest_until = now
            self.used_key = None
        if not self.active:
            return None
        if now >= self.deadline:
            self.stop('30-second demo complete — R to restart')
            return None
        if self.command is not None:
            if now < self.until:
                self.reason = f'Searching: {self.command}'
                return self.command
            self.command = None
            self.rest_until = now + REST_S
            self.used_key = obs.key
        if now >= self.rest_until and obs.key != self.used_key:
            self.command = self.rng.choice(['F', 'F', 'F', 'L', 'R'])
            self.until = now + PULSE_S
            self.reason = f'Searching: {self.command}'
            return self.command
        self.reason = 'Stopped between bursts; watching camera'
        return None


class HubFeed:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.current = None
        self.error = 'Connecting to local hub...'

    def fetch(self):
        from bobapp.edge.api.auth import load_token

        token = load_token("BOB_EDGE_TOKEN")
        started = time.monotonic()
        def get(path):
            headers = {'Authorization': f'Bearer {token}'} if token else {}
            with urlopen(Request(self.url + path, headers=headers), timeout=0.4) as response:
                data = response.read(1048577)
                if len(data) > 1048576:
                    raise ValueError('Hub response too large')
                return json.loads(data)
        page = get('/v1/observations?workspace=rover&source_mode=LIVE&delivery=realtime&latest=true&limit=1')
        status = get('/v1/status?workspace=rover')
        return observation(status, page, started, time.monotonic())

    async def poll(self):
        # Contract imports load OpenCV. Keep its SDL separate from pygame on macOS.
        context = multiprocessing.get_context('spawn')
        updates = context.Queue(maxsize=1)
        worker = context.Process(target=_feed_worker, args=(self.url, updates), daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                try:
                    self.current, self.error = updates.get_nowait()
                except queue.Empty:
                    pass
                await asyncio.sleep(0.02)
            self.current = None
            self.error = 'Feed worker exited; restart the demo'
        finally:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=1)
            updates.close()


def _feed_worker(url, updates):
    feed = HubFeed(url)
    while True:
        try:
            result = (feed.fetch(), '')
        except Exception:
            # Never print request headers, tokens or response bodies.
            result = (None, 'No fresh feed. Check hub, Jetson stream and .env token.')
        try:
            updates.put_nowait(result)
        except queue.Full:
            pass  # Bounded queue: parent also checks each observation's expiry.
        time.sleep(0.1)


async def run(url):
    import pygame
    from bleak import BleakClient, BleakScanner

    pygame.init()
    feed = HubFeed(url)
    poller = asyncio.create_task(feed.poll())
    try:
        print('Looking for BOB; close the arrow-key remote first.', flush=True)
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: (ad.local_name or d.name) in {'BOB-ControllerBench', 'BOB-MotorTest'}, timeout=15)
        if device is None:
            raise RuntimeError('BOB not found; check power and other BLE clients')
        async with BleakClient(device) as client:
            remote = Remote(client, legacy=client.services.get_characteristic(STATUS_UUID) is None)
            try:
                await remote.stop()
                if remote.legacy:
                    await remote.send(b'3')
                screen = pygame.display.set_mode((850, 300))
                pygame.display.set_caption('BOB — supervised wander demo')
                font = pygame.font.Font(None, 26)
                wander = Wander()
                running = focused = True
                next_send = 0.0
                print('R starts; Space stops; Esc quits. Person detection latches STOP.', flush=True)
                while running and client.is_connected:
                    start = stop = False
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False
                        elif event.type == pygame.WINDOWFOCUSLOST:
                            focused = False
                            stop = True
                        elif event.type == pygame.WINDOWFOCUSGAINED:
                            focused = True
                        elif event.type == pygame.KEYDOWN:
                            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                                running = False
                            elif event.key in (pygame.K_SPACE, pygame.K_s):
                                stop = True
                            elif event.key == pygame.K_r and not getattr(event, 'repeat', False):
                                start = True
                    now = time.monotonic()
                    command = wander.update(feed.current, now, start=start,
                                            stop=stop or not focused or not running)
                    if command is None:
                        if remote.moving:
                            await remote.stop()
                    elif not remote.moving or now >= next_send:
                        await remote.move(command)
                        next_send = now + 0.1
                    screen.fill((22, 27, 34))
                    lines = ['Mac Bluetooth + existing Jetson detections',
                             'Cleared floor / supervised demo — no obstacle avoidance',
                             'R: start search     Space: STOP     Esc: quit', wander.reason,
                             feed.error or 'Live Jetson feed connected',
                             (feed.current.ppe if feed.current else 'PPE: waiting')[:100]]
                    for i, line in enumerate(lines):
                        screen.blit(font.render(line, True, (235, 240, 245)), (20, 20 + i * 44))
                    pygame.display.flip()
                    await asyncio.sleep(0.02)
            finally:
                if client.is_connected:
                    with suppress(Exception):
                        await remote.stop()
    finally:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hub-url', default='http://127.0.0.1:8780')
    args = parser.parse_args()
    # Keep the bearer token on the operator's existing local hub.
    if args.hub_url not in {'http://127.0.0.1:8780', 'http://localhost:8780'}:
        parser.error('Use the local hub on port 8780')
    try:
        asyncio.run(run(args.hub_url))
    except KeyboardInterrupt:
        print('Stopped.')
    except Exception as error:
        raise SystemExit(f'Wander demo stopped: {type(error).__name__}') from error


if __name__ == '__main__':
    main()
