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
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from hardware.controller_protocol import STATUS_UUID, decode_status, encode_tone
from hardware.esp32.remote import Remote

MAX_AGE_S = 1.0
PULSE_S = 0.35
REST_S = 0.2
TURN_S = 0.6
INSPECT_S = 4.0
TURN_AWAY_S = 4.0
SPEECH_COOLDOWN_S = 10.0
RECOVERY_S = 2.0
RECHECK_S = 3.0


@dataclass(frozen=True)
class Observation:
    identity: tuple
    key: str
    person: bool
    expires: float
    ppe: str
    subject: tuple | None = None
    missing: tuple[str, ...] = ()
    photo_sha: str | None = None


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
    people = [box for box in event.boxes if box.source == 'model'
              and box.cls_name == 'person' and box.conf >= 0.5]
    width, height = event.image_size.width, event.image_size.height
    candidates = [box for box in people if box.conf >= 0.75
                  and (box.xyxy[2] - box.xyxy[0]) * (box.xyxy[3] - box.xyxy[1]) >= width * height * .02
                  and box.xyxy[3] - box.xyxy[1] >= height * .2]
    subject = max(candidates, key=lambda box: box.conf, default=None)
    missing = set()
    if subject is not None and len(people) == 1:
        x1, y1, x2, y2 = subject.xyxy
        for verdict in record.body.verdicts:
            box = verdict.violation
            if verdict.verdict == 'not_wearing' and box is not None and box.source == 'derived':
                cx, cy = (box.xyxy[0] + box.xyxy[2]) / 2, (box.xyxy[1] + box.xyxy[3]) / 2
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    missing.add(verdict.rule)
    ppe = ', '.join(f'{name}: {verdict.value}' for name, verdict in record.body.frame_verdicts.items())
    return Observation((record.edge_id, str(record.store_epoch), record.run_id,
                        str(event.session_id)), str(event.event_id), subject is not None,
                       now + MAX_AGE_S - age, ppe or 'PPE unverified',
                       tuple(subject.xyxy) if subject else None, tuple(sorted(missing)),
                       record.body.evidence_sha256)


def same_subject(a, b):
    if a is None or b is None:
        return False
    x1, y1, x2, y2 = a
    u1, v1, u2, v2 = b
    overlap = max(0, min(x2, u2) - max(x1, u1)) * max(0, min(y2, v2) - max(y1, v1))
    union = (x2-x1)*(y2-y1) + (u2-u1)*(v2-v1) - overlap
    return union > 0 and overlap / union >= .3



class Wander:
    """Turn-led search -> brief inspection -> speech if confirmed -> turn away."""
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.turn = self.rng.choice(['L', 'R'])
        self.enabled = False
        self.recover_since = None
        self.active = False
        self.reason = 'Press R once to start; Space pauses'
        self.identity = None
        self.command = None
        self.until = self.rest_until = 0.0
        self.used_key = self.latest_key = None
        self.key_since = 0.0
        self.phase = 'SEARCH'
        self.turn_count = 0
        self.last_speech = -float('inf')
        self.announce = False
        self.report = None
        self.photo = None
        self.evidence = {}
        self.subject = None
        self.clear_since = None

    def stop(self, reason, *, manual=True):
        if manual:
            self.enabled = False
        self.recover_since = None
        self.active = False
        self.command = None
        self.phase = 'SEARCH'
        self.reason = (reason if self.enabled or manual else
                       reason.split(';')[0] + ' — press R to enable')

    def turn_away(self, now):
        self.phase = 'TURN_AWAY'
        self.until = now + TURN_AWAY_S
        self.away_started = now
        self.clear_since = None
        self.command = self.turn
        self.reason = 'Turning away from inspected view'
        return self.turn

    def update(self, obs, now, *, start=False, stop=False):
        self.announce = False
        self.report = None
        if stop:
            self.stop('Paused — R to restart')
            return None
        if start:
            self.enabled = True
        if obs is None or now >= obs.expires:
            self.stop('Waiting for feed; resumes after 2 healthy seconds', manual=False)
            return None
        fresh = obs.key != self.latest_key
        if fresh:
            self.latest_key, self.key_since = obs.key, now
        elif now - self.key_since >= MAX_AGE_S:
            self.stop('Frozen feed; resumes after 2 healthy seconds', manual=False)
            return None
        if self.identity is not None and obs.identity != self.identity:
            self.identity = obs.identity
            self.stop('Camera session changed; waiting for healthy feed', manual=False)
            return None
        self.identity = obs.identity
        if self.enabled and not self.active:
            if self.recover_since is None:
                self.recover_since = now
            if not start and now - self.recover_since < RECOVERY_S:
                self.reason = 'Feed recovering — resuming automatically'
                return None
            self.active = True
            self.rest_until = now
            self.used_key = None
            self.phase = 'SEARCH'
            self.turn_count = 0
        if not self.active:
            return None
        if self.phase == 'RECHECK':
            if now < self.rest_until:
                self.reason = 'Stopped briefly; automatically checking again'
                return None
            self.phase = 'SEARCH'
        if self.phase == 'SPEAK':
            if now < self.until:
                self.reason = 'Missing PPE — stopped for announcement'
                return None
            return self.turn_away(now)
        if self.phase == 'TURN_AWAY':
            if obs.person:
                self.clear_since = None
            elif fresh and self.clear_since is None:
                self.clear_since = now
            if (now - self.away_started >= 1.0 and self.clear_since is not None
                    and now - self.clear_since >= .4):
                self.phase = 'SEARCH'
                self.command = None
                self.rest_until = now + REST_S
                self.used_key = obs.key
            elif now >= self.until:
                self.command = None
                self.phase = 'RECHECK'
                self.rest_until = now + RECHECK_S
                self.reason = 'View still occupied; pausing before automatic recheck'
                return None
            else:
                self.reason = 'Turning away; waiting for person to leave view'
                return self.turn
        if self.phase == 'SEARCH' and obs.person:
            self.phase = 'INSPECT'
            self.command = None
            self.inspect_started = now
            self.subject = obs.subject
            self.evidence = {}
            self.photo = None
            self.inspection_key = obs.key
        if self.phase == 'INSPECT':
            self.reason = 'Checking person/PPE briefly'
            confirmed = ()
            # Count distinct frames after the stop, matched to the same image subject.
            if fresh and obs.key != self.inspection_key and now - self.inspect_started >= .3:
                if not same_subject(self.subject, obs.subject):
                    self.evidence = {}
                    self.photo = None
                self.subject = obs.subject
                if obs.person and obs.photo_sha:
                    self.photo = obs
                # A brief UNVERIFIED gap may occur between real positives. Keep at
                # most 0.75 s of same-subject evidence; never announce on that gap.
                self.evidence = {rule: evidence for rule, evidence in self.evidence.items()
                                 if now - evidence[2] <= .75}
                for rule in obs.missing if obs.person else ():
                    count, since, _ = self.evidence.get(rule, (0, now, now))
                    self.evidence[rule] = (count + 1, since, now)
                confirmed = tuple(rule for rule in obs.missing if rule in self.evidence
                                  and self.evidence[rule][0] >= 2
                                  and now - self.evidence[rule][1] >= .25)
            self.reason = ('Confirming Missing PPE: ' + ', '.join(obs.missing)
                           if obs.missing else 'PPE unverified — waiting for clearer evidence')
            if confirmed or now - self.inspect_started >= INSPECT_S:
                # Keep IDs/hashes pointing to the existing Jetson image and website record.
                evidence = obs if confirmed else (self.photo or obs)
                self.report = {'event_id': evidence.key, 'identity': evidence.identity,
                               'evidence_sha256': evidence.photo_sha,
                               'source_mode': 'LIVE', 'delivery': 'realtime',
                               'confirmed_missing': list(confirmed),
                               'result': 'missing_ppe' if confirmed else 'unverified',
                               'speech_requested': False,
                               'speech_reason': 'cooldown' if confirmed else 'unverified'}
                if confirmed and now - self.last_speech >= SPEECH_COOLDOWN_S:
                    self.announce = True
                    self.report['speech_requested'] = True
                    self.report['speech_reason'] = 'confirmed'
                    self.last_speech = now
                    self.phase = 'SPEAK'
                    self.until = now + 1.5
                    return None
                return self.turn_away(now)
            return None
        if self.command is not None:
            if now < self.until:
                self.reason = f'Scanning: {self.command}'
                return self.command
            self.command = None
            self.rest_until = now + REST_S
            self.used_key = obs.key
        if now >= self.rest_until and obs.key != self.used_key:
            # Two short forward steps, then one turn; avoid endless in-place sweeps.
            if self.turn_count == 0:
                self.turn = self.rng.choice(['L', 'R'])
            self.command = 'F' if self.turn_count < 2 else self.turn
            self.turn_count = (self.turn_count + 1) % 3
            self.until = now + (TURN_S if self.command != 'F' else PULSE_S)
            self.reason = f'Scanning: {self.command}'
            return self.command
        self.reason = 'Watching between scan turns'
        return None


async def say_missing(remote):
    """Existing speech-1 firmware command. MotorTest's beep is not speech."""
    await remote.stop()
    if remote.legacy:
        return 'unsupported_on_MotorTest'
    status = decode_status(bytes(await asyncio.wait_for(
        remote.client.read_gatt_char(STATUS_UUID), 1.0)))
    await remote.send(encode_tone(status.session))
    return 'write_acknowledged'


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

    feed = HubFeed(url)
    poller = None
    stage = 'Bluetooth scan'
    try:
        print('Looking for BOB; close the arrow-key remote first.', flush=True)
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: (ad.local_name or d.name) in {'BOB-ControllerBench', 'BOB-MotorTest'}, timeout=15)
        if device is None:
            raise RuntimeError('BOB not found; check power and other BLE clients')
        stage = 'Bluetooth connection'
        print(f'Found {device.name or "BOB"}; connecting...', flush=True)
        async with BleakClient(device) as client:
            stage = 'controller initialization'
            remote = Remote(client, legacy=client.services.get_characteristic(STATUS_UUID) is None)
            try:
                await remote.stop()
                if remote.legacy:
                    await remote.send(b'3')
                stage = 'remote window'
                pygame.init()
                poller = asyncio.create_task(feed.poll())
                screen = pygame.display.set_mode((850, 300))
                pygame.display.set_caption('BOB — supervised wander demo')
                font = pygame.font.Font(None, 26)
                wander = Wander()
                running = focused = True
                next_send = 0.0
                print('R starts; Space stops; Esc quits. Inspect, announce, then turn away.', flush=True)
                log_dir = Path('runs/wander') / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                log_dir.mkdir(parents=True, exist_ok=True)
                print(f'Inspection log: {log_dir / "inspections.jsonl"}', flush=True)
                speaking = False
                last_result = ''
                stage = 'running demo'
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
                    if (command is None and remote.moving) or (speaking and wander.phase != 'SPEAK'):
                        await remote.stop()
                        speaking = False
                    if wander.announce:
                        delivery = await say_missing(remote)
                        speaking = delivery == 'write_acknowledged'
                        wander.report['speech_delivery'] = delivery
                        # Allow the full clip after the BLE acknowledgement before moving.
                        wander.until = time.monotonic() + 1.5
                    if wander.report is not None:
                        report = {**wander.report, 'mac_logged_wall_ns': time.time_ns()}
                        with (log_dir / 'inspections.jsonl').open('a') as log:
                            log.write(json.dumps(report) + '\n')
                        last_result = ('Photo saved on Jetson; website sync uses existing archive'
                                       if report['evidence_sha256'] else 'No saved photo reported by Jetson')
                        print(json.dumps(report), flush=True)
                    if command is not None and (not remote.moving or now >= next_send):
                        await remote.move(command)
                        next_send = now + 0.1
                    screen.fill((22, 27, 34))
                    lines = ['Mac Bluetooth + existing Jetson detections',
                             'Cleared floor / supervised demo — no obstacle avoidance',
                             'R: start once     Space: PAUSE     Esc: quit', wander.reason,
                             feed.error or last_result or 'Live Jetson feed connected',
                             (feed.current.ppe if feed.current else 'PPE: waiting')[:100]]
                    for i, line in enumerate(lines):
                        screen.blit(font.render(line, True, (235, 240, 245)), (20, 20 + i * 44))
                    pygame.display.flip()
                    await asyncio.sleep(0.02)
            finally:
                if client.is_connected:
                    with suppress(Exception):
                        await remote.stop()
    except Exception as error:
        raise RuntimeError(f'{stage}: {type(error).__name__}: {error}') from error
    finally:
        if poller is not None:
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
        raise SystemExit(f'Wander demo stopped: {error}') from error


if __name__ == '__main__':
    main()
