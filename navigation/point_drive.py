"""Jetson-local supervised click-to-floor demo. Motors disabled unless --execute."""
import argparse
import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from bobapp.edge.api.auth import load_token, token_ok
from navigation.feed import latest
from navigation.point_control import PointSupervisor
from navigation.point_geometry import CameraView
from navigation.run_source import read_run_info
from vision.schema import StreamHealth


class Runtime:
    def __init__(self, directory, height, yaw, execute=False, ble_name='BOB-ControllerBench'):
        self.directory = Path(directory)
        self.info = read_run_info(self.directory)
        if execute and self.info['source_mode'] != 'LIVE':
            raise ValueError('physical execution requires a LIVE server run')
        self.height, self.yaw, self.execute, self.ble_name = height, yaw, execute, ble_name
        self.supervisor = PointSupervisor(height, yaw, started=time.monotonic())
        self.link = None
        self.abort = asyncio.Event()
        self.pulse_task = None
        self.snapshot = None
        self.views = OrderedDict()
        self.owner = None
        self.closing = False
        self.trace = None

    def record(self, kind, **details):
        if self.trace:
            self.trace.write(json.dumps({'kind': kind, 'monotonic_s': time.monotonic(),
                'wall_ns': time.time_ns(), 'run_id': self.info['run_id'],
                'source_mode': self.info['source_mode'], 'execute': self.execute, **details})+'\n')

    def read(self):
        if read_run_info(self.directory) != self.info:
            raise RuntimeError('vision server run changed; restart point driver')
        with (self.directory/'point_frame.json').open('rb') as file:
            raw = file.read(4*1024*1024+1)
        if len(raw) > 4*1024*1024:
            raise ValueError('point preview exceeds size limit')
        data = json.loads(raw)
        view = CameraView.parse(data, self.info)
        health = latest(self.directory/'stream_health.jsonl', StreamHealth)
        return data, view, health

    def stop(self):
        self.supervisor.revoke()
        self.abort.set()
        self.record('operator_stop')

    async def pulse(self, request):
        try:
            self.record('pulse_requested', direction=request.direction,
                        event_id=request.event_id, pulse_ms=request.pulse_ms)
            if self.link:
                sent = await self.link.pulse(request,
                    lambda: self.supervisor.allowed(request, time.monotonic()), self.abort)
            else:
                sent = False
                try:
                    await asyncio.wait_for(self.abort.wait(), request.pulse_ms/1000)
                except asyncio.TimeoutError:
                    pass
            self.record('pulse_finished', motion_write_acknowledged=sent,
                        controller_status=asdict(self.link.last_status) if self.link and self.link.last_status else None)
        except Exception as exc:
            self.supervisor.fail(str(exc))
            self.stop()
        finally:
            self.supervisor.finished(time.time_ns(), time.monotonic())

    async def monitor(self):
        try:
            await self._monitor()
        except Exception as exc:
            # A failed monitor must not leave an apparently ready operator page.
            self.supervisor.fail(str(exc))
            self.snapshot = None
            self.record('monitor_failed', error=str(exc))
        finally:
            self.stop()

    async def _monitor(self):
        s = self.supervisor
        while not self.closing:
            try:
                data, view, health = await asyncio.to_thread(self.read)
                self.snapshot = data
                self.views[str(view.event.event_id)] = view
                while len(self.views) > 8:
                    self.views.popitem(last=False)
                s.update(view.event, health, time.time_ns(), time.monotonic())
            except RuntimeError as exc:
                s.fail(str(exc))
                s.update(None, None, time.time_ns(), time.monotonic())
                self.snapshot = None
            except (OSError, ValueError, KeyError, TypeError) as exc:
                s.update(None, None, time.time_ns(), time.monotonic())
                s.pause(f'waiting for valid point preview: {exc}')
                self.snapshot = None
            if s.active and not s.allowed(s.active, time.monotonic(), continuing=True):
                self.abort.set()
            if self.pulse_task and self.pulse_task.done():
                self.pulse_task.result()
                self.pulse_task = None
            if self.pulse_task is None:
                request = s.request()
                if request is not None:
                    self.abort.clear()
                    self.pulse_task = asyncio.create_task(self.pulse(request))
            await asyncio.sleep(.025)

    def status(self):
        s = self.supervisor
        state, reason = s.phase()
        return {'state': state, 'reason': reason, 'held': s.held,
                'release_required': s.release_required, 'distance_m': s.distance,
                'heading_error_rad': s.heading_error, 'target': s.target,
                'attempts': s.attempts, 'max_steps': s.settings.max_steps,
                'mode': 'EXECUTE' if self.execute else 'DRY_RUN', 'source_mode': self.info['source_mode']}


def create_app(runtime, token, port=8790):
    if not token:
        raise ValueError('BOB_EDGE_TOKEN is required for the point driver')

    @asynccontextmanager
    async def lifespan(app):
        lock = (runtime.directory/'.point-driving.lock').open('a')
        task = None
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if runtime.execute:
                from navigation.drive import PulseLink
                runtime.link = await PulseLink.connect(runtime.ble_name)
            runtime.supervisor.started = time.monotonic()
            runtime.trace = (runtime.directory/f'point_drive_{uuid4()}.jsonl').open('w', buffering=1)
            runtime.record('started', run_info=runtime.info, height_m=runtime.height,
                           forward_yaw_offset_deg=runtime.yaw)
            task = asyncio.create_task(runtime.monitor())
            yield
        finally:
            runtime.closing = True
            runtime.stop()
            try:
                if task:
                    await task
                if runtime.pulse_task:
                    await runtime.pulse_task
            finally:
                try:
                    if runtime.link:
                        await runtime.link.close()
                finally:
                    if runtime.trace:
                        runtime.trace.close()
                    lock.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get('/', response_class=HTMLResponse)
    def page():
        return HTMLResponse(Path(__file__).with_name('point_drive.html').read_text(),
                            headers={'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY'})

    @app.get('/api/frame')
    async def frame(authorization: str = Header('')):
        if not token_ok(token, authorization):
            raise HTTPException(401, 'authentication required')
        data = runtime.snapshot
        if data is None:
            raise HTTPException(503, 'waiting for --point-preview output')
        view = runtime.views.get(data['event']['event_id'])
        marker = None
        if view and runtime.supervisor.target:
            marker = view.project(runtime.supervisor.target)
        return JSONResponse({'event_id': data['event']['event_id'], 'jpeg': data['jpeg'],
                             'marker': marker, 'status': runtime.status()},
                            headers={'Cache-Control': 'no-store'})

    @app.websocket('/control')
    async def control(ws: WebSocket):
        if ws.headers.get('origin') not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
            await ws.close(code=1008)
            return
        await ws.accept()
        owner = str(uuid4())
        try:
            auth = await asyncio.wait_for(ws.receive_json(), 3)
            if not isinstance(auth, dict) or not token_ok(token, 'Bearer '+str(auth.get('token', ''))):
                await ws.close(code=1008)
                return
            if runtime.owner is not None:
                await ws.close(code=1008, reason='another operator is connected')
                return
            runtime.owner = owner
            runtime.stop()
            runtime.supervisor.sequence = -1
            message = None
            while not runtime.closing:
                ticket, issued = str(uuid4()), time.monotonic()
                await ws.send_json({**runtime.status(), 'ticket': ticket, 'message': message})
                message = None
                raw = await asyncio.wait_for(ws.receive_text(), .35)
                data = json.loads(raw) if len(raw) <= 2048 else None
                now = time.monotonic()
                if (not isinstance(data, dict) or data.get('ticket') != ticket or now-issued > .3):
                    raise ValueError('operator response expired or invalid')
                kind = data.get('kind')
                s = runtime.supervisor
                if kind == 'hold':
                    s.control(data.get('held'), data.get('sequence'), now)
                    if not s.held:
                        runtime.abort.set()
                elif kind == 'select':
                    runtime.stop()
                    s.control(False, data.get('sequence'), now)
                    view = runtime.views.get(data.get('event_id'))
                    try:
                        if view is None:
                            raise ValueError('displayed frame expired; select on the current image')
                        s.select(view, data.get('u'), data.get('v'), now)
                        runtime.record('target', source_event_id=str(view.event.event_id),
                                       target=s.target, height_m=s.height, yaw_offset_rad=s.yaw_offset,
                                       u=data.get("u"), v=data.get("v"),
                                       source_camera=view.packet.model_dump(mode="json"))
                    except ValueError as exc:
                        s.clear_target()
                        message = str(exc)
                else:
                    raise ValueError('unknown control message')
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, TypeError):
            pass
        finally:
            if runtime.owner == owner:
                runtime.stop()
                runtime.owner = None
            try:
                await ws.close()
            except RuntimeError:
                pass

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--camera-height-m', type=float, default=.10922,
                        help='camera lens height above floor; mounted BOB default 4.3 inches')
    parser.add_argument('--forward-yaw-offset-deg', type=float,
                        help='measured rover-forward yaw minus camera yaw; 0 for aligned forward axes')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--ble-name', default='BOB-ControllerBench')
    parser.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    if args.execute and args.forward_yaw_offset_deg is None:
        parser.error('--execute requires an explicit --forward-yaw-offset-deg calibration')
    if not 1024 <= args.port <= 65535:
        parser.error('port must be within 1024..65535')
    try:
        runtime = Runtime(args.run_dir, args.camera_height_m, args.forward_yaw_offset_deg or 0,
                          args.execute, args.ble_name)
        app = create_app(runtime, load_token('BOB_EDGE_TOKEN'), args.port)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    import uvicorn
    print(f"{'PHYSICAL STEPS' if args.execute else 'DRY RUN: motors disabled'}: "
          f"http://127.0.0.1:{args.port} (use SSH forwarding from the Mac).", flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, ws_max_size=2048, timeout_graceful_shutdown=5)


if __name__ == '__main__':
    main()
