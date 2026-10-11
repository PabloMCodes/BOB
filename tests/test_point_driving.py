"""Point-driving geometry, expiring permission and transport; no physical hardware."""
import asyncio
import base64
from dataclasses import replace
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from navigation.demo import observation, PERSON
from navigation.drive import PulseLink
from navigation.point_control import PointSupervisor
from navigation.point_drive import Runtime, create_app
from navigation.point_geometry import CameraView
from tests.test_supervised_drive import FakeClient
from vision.config import load_config
from vision.pipeline import FrameResult
from vision.schema import FramePacket, ImageSize
from vision.server.detection import detection_event
from vision.server.point_preview import PointPreviewWriter
from vision.server.transport import FrameServer

INFO = {'run_info_version': 1, 'producer': 'vision.server', 'run_id': str(uuid4()),
        'source_mode': 'SAMPLE', 'started_ts_ns': 1}
JPEG = cv2.imencode('.jpg', np.full((480, 640, 3), 120, np.uint8))[1].tobytes()


def camera(seq=0, seconds=0., orientation='landscape_left', **kwargs):
    event, health, wall, mono = observation(seq, seconds, **kwargs)
    yaw = event.pose.yaw_rad
    matrix = np.array([[math.cos(yaw), 0, math.sin(yaw), event.pose.x_m],
                       [0, 1, 0, event.pose.y_m],
                       [-math.sin(yaw), 0, math.cos(yaw), event.pose.z_m], [0, 0, 0, 1.]])
    packet = FramePacket(schema_version=2, msg_type='frame', session_id=event.session_id,
        seq_id=seq, iphone_frame_ts_ns=event.iphone_frame_ts_ns, tracking_state='normal',
        camera_transform=matrix.T.reshape(-1).tolist(),
        image=dict(width=640, height=480, encoding='jpeg', device_orientation=orientation, byte_length=len(JPEG)),
        intrinsics=dict(fx=500, fy=500, cx=319.5, cy=239.5, ref_width=640, ref_height=480))
    # Use the actual admission/association path to construct the internal preview fixture.
    server = FrameServer(load_config())
    received = server.admit(packet, JPEG, wall)
    w, h = (480, 640) if orientation.startswith('portrait') else (640, 480)
    result = FrameResult(event.boxes, [], ImageSize(width=w, height=h), 0., 0, [])
    event = detection_event(received, result, 'SYNTHETIC', server.associator.associate(packet, received.gap_ns))
    data = {'version': 1, 'run_info': INFO, 'packet': packet.model_dump(mode='json'),
            'event': event.model_dump(mode='json'), 'orientation': orientation,
            'jpeg': base64.b64encode(JPEG).decode()}
    return CameraView.parse(data, INFO), health, wall, mono, data, received


@pytest.mark.parametrize('orientation', ['landscape_left','landscape_right','portrait','portrait_upside_down'])
def test_world_target_pixel_round_trip_all_orientations(orientation):
    view, *_ = camera(orientation=orientation)
    target = (0.1, -.10922, -.7)
    pixel = view.project(target)
    assert pixel is not None
    assert view.floor_target(*pixel, -.10922) == pytest.approx(target)


def test_projection_scales_intrinsics_and_uses_yaw_and_translation():
    view, *_ = camera(x=1., z=-.2, yaw=math.pi/2)
    k = view.packet.intrinsics
    larger = k.model_copy(update={key:getattr(k,key)*2 for key in ('fx','fy','cx','cy','ref_width','ref_height')})
    other = replace(view, packet=view.packet.model_copy(update={'intrinsics':larger}))
    assert other.floor_target(.5,.7,-.10922) == pytest.approx(view.floor_target(.5,.7,-.10922))
    target = view.floor_target(.5,.7,-.10922)
    assert target[0] < 1 and target[2] == pytest.approx(-.2)


@pytest.mark.parametrize('u,v', [(True,.8),(-.1,.8),(.5,float('nan')),(.5,.1),(.5,.5),(.5,.51)])
def test_invalid_click_horizon_and_distant_target_rejected(u,v):
    view,*_=camera()
    with pytest.raises(ValueError):view.floor_target(u,v,-.10922)


def test_missing_intrinsics_invalid_pose_and_behind_camera():
    view,*_=camera()
    with pytest.raises(ValueError):replace(view,packet=view.packet.model_copy(update={'intrinsics':None})).floor_target(.5,.7,-.10922)
    with pytest.raises(ValueError):replace(view,event=view.event.model_copy(update={'pose_valid':False})).floor_target(.5,.7,-.10922)
    assert view.project((0,-.1,1)) is None


@pytest.mark.parametrize('mutation', ['run','event','size','pose','orientation','rotation','root'])
def test_snapshot_identity_mismatch_is_rejected(mutation):
    *_, data, received=camera()
    if mutation=='run': data['run_info']={**INFO,'run_id':str(uuid4())}
    if mutation=='event':data['event']['seq_id']+=1
    if mutation=='size':data['event']['image_size']['width']=100
    if mutation=='pose':data['event']['pose']['x_m']=10
    if mutation=='orientation':data['orientation']='unknown'
    if mutation=='rotation':data['orientation']='landscape_right'
    if mutation=='root':data=[]
    with pytest.raises(ValueError):CameraView.parse(data,INFO)


def ready():
    s=PointSupervisor(.10922,0,started=0)
    for seq,t in enumerate((0.,.15,.3)):
        view,h,w,m,*_=camera(seq,t)
        s.update(view.event,h,w,m)
    s.select(view,.5,.7,.3)
    s.control(False,0,.3)
    s.control(True,1,.3)
    assert s.phase()[0]=='READY'
    return s


def test_selection_alone_never_moves_release_and_expiry_stop():
    s=ready()
    s.control(False,2,.31)
    assert s.request() is None
    s.control(True,3,.32)
    request=s.request()
    assert request and request.direction=='forward' and request.pulse_ms==100
    assert s.allowed(request,.33)
    assert not s.allowed(request,.63,continuing=True)
    s.control(True,4,.64)  # Late heartbeat cannot silently restart a hold.
    assert not s.held and s.release_required


def test_turn_direction_arrival_and_no_queued_authorization():
    s=ready()
    s.target=(-.7,-.10922,-.5)
    s.update(*observation(4,.4))
    assert s.decision.suggested_direction=='turn_left'
    s.target=(.7,-.10922,-.5)
    s.update(*observation(5,.45))
    assert s.decision.suggested_direction=='turn_right'
    s.target=(0,-.10922,-.1)
    s.update(*observation(6,.5))
    assert s.phase()[0]=='ARRIVED' and s.request() is None
    s.control(True,2,.51)
    assert not s.held


@pytest.mark.parametrize('failure', ['person','stale','session','pose'])
def test_interruption_revokes_hold_and_requires_deliberate_reauthorization(failure):
    s=ready();request=s.request()
    args=list(observation(4,.4,boxes=(PERSON,) if failure=='person' else ()))
    if failure=='stale':args[2]+=1_000_000_000
    if failure=='session':args[1]=args[1].model_copy(update={'session_id':uuid4()})
    if failure=='pose':args[0]=args[0].model_copy(update={'pose_valid':False,'pose':None})
    s.update(*args)
    assert not s.allowed(request,.4,continuing=True) and s.release_required
    if failure!='person':assert s.target is None


def test_stale_or_failed_selection_clears_old_target():
    s=ready(); view,*_=camera(0,0)
    s.update(*observation(5,.8))
    with pytest.raises(ValueError):s.select(view,.5,.7,.8)
    assert s.target is None and s.request() is None


def test_fake_radio_release_ends_with_stop_and_one_bounded_packet():
    async def scenario():
        client=FakeClient();link=PulseLink(client,clock=lambda:.3)
        s=ready();request=s.request();abort=asyncio.Event()
        await link.pulse(request,lambda:s.allowed(request,.3),abort)
        from hardware.controller_protocol import PacketType
        packets=[p for p in client.writes if p[1]==PacketType.MOTION]
        assert len(packets)==1 and not client.moving and not client.armed
    asyncio.run(scenario())


def test_point_preview_writer_emits_consistent_pair_and_reports_errors(tmp_path):
    view,_,_,_,_,received=camera()
    detection=SimpleNamespace(event=view.event,image=np.full((480,640,3),120,np.uint8))
    writer=PointPreviewWriter(tmp_path,INFO,'landscape_left')
    writer.submit(received,detection)
    deadline=time.monotonic()+3
    while writer.written<1 and time.monotonic()<deadline:time.sleep(.01)
    stats=writer.close()
    assert stats['written']==1 and stats['errors']==0
    data=json.loads((tmp_path/'point_frame.json').read_text())
    restored=CameraView.parse(data,INFO)
    assert restored.event==view.event and restored.packet==view.packet
    assert base64.b64decode(data['jpeg']).startswith(b'\xff\xd8')


def runtime_fixture(tmp_path,monkeypatch):
    (tmp_path/'run_info.json').write_text(json.dumps(INFO))
    r=Runtime(tmp_path,.10922,0)
    sequence=[0]
    def read():
        sequence[0]+=1
        view,h,wall,_,data,_=camera(sequence[0],sequence[0]*.03)
        now=time.time_ns()
        event=view.event.model_copy(update={'jetson_receive_ts_ns':now})
        health=h.model_copy(update={'emitted_ts_ns':now,'last_rx_ts_ns':now})
        data['event']=event.model_dump(mode='json')
        return data,replace(view,event=event),health
    monkeypatch.setattr(r,'read',read)
    return r


def test_runtime_refuses_physical_replay_and_changed_run(tmp_path):
    (tmp_path/'run_info.json').write_text(json.dumps(INFO))
    with pytest.raises(ValueError):Runtime(tmp_path,.10922,0,execute=True)
    r=Runtime(tmp_path,.10922,0)
    (tmp_path/'run_info.json').write_text(json.dumps({**INFO,'run_id':str(uuid4())}))
    with pytest.raises(RuntimeError):r.read()


def test_unexpected_monitor_failure_revokes_hold_and_reports_fault(tmp_path, monkeypatch):
    (tmp_path/'run_info.json').write_text(json.dumps(INFO))
    r = Runtime(tmp_path, .10922, 0)
    r.supervisor = ready()
    r.snapshot = {'old': 'preview'}

    def broken_read():
        raise AttributeError('invalid run identity')

    monkeypatch.setattr(r, 'read', broken_read)
    asyncio.run(r.monitor())
    assert r.supervisor.phase() == ('FAULT', 'invalid run identity')
    assert r.abort.is_set() and r.snapshot is None
    assert not r.supervisor.held and r.supervisor.release_required


def test_person_interruption_cannot_reuse_a_hold_after_clear_frames():
    s = ready()
    s.update(*observation(4, .4, boxes=(PERSON,)))
    assert s.target is not None and not s.held
    for seq, seconds in enumerate((.5, 1., 1.6, 1.8, 2.), start=5):
        s.update(*observation(seq, seconds))
        s.control(True, seq, seconds)
    assert s.decision.state == 'EXPLORE'
    assert s.release_required and s.request() is None
    s.control(False, 20, 2.)
    s.control(True, 21, 2.)
    assert s.request() is not None


@pytest.mark.parametrize('failure', ['frozen', 'tracking', 'new_session', 'health'])
def test_target_and_floor_are_cleared_on_camera_interruption(failure):
    s = ready()
    args = list(observation(4, .4))
    if failure == 'frozen':
        args[0] = s.event
        args[2] += 1_000_000_000
    elif failure == 'tracking':
        args[1] = args[1].model_copy(update={'tracking_state': 'limited'})
    elif failure == 'new_session':
        args[0] = args[0].model_copy(update={'session_id': uuid4()})
        args[1] = args[1].model_copy(update={'session_id': args[0].session_id})
    else:
        args[1] = None
    s.update(*args)
    assert s.target is None and s.floor_y is None
    assert not s.held and s.release_required and s.request() is None


def test_preview_encode_failure_is_reported_without_replacing_good_frame(tmp_path, monkeypatch):
    view, _, _, _, _, received = camera()
    path = tmp_path/'point_frame.json'
    path.write_text('previous frame')
    monkeypatch.setattr(cv2, 'imencode', lambda *args: (False, None))
    writer = PointPreviewWriter(tmp_path, INFO, 'landscape_left')
    try:
        writer.submit(received, SimpleNamespace(event=view.event, image=np.zeros((480,640,3), np.uint8)))
        deadline = time.monotonic()+3
        while not writer.errors and time.monotonic() < deadline:
            time.sleep(.01)
    finally:
        stats = writer.close()
    assert stats['errors'] == 1 and stats['written'] == 0 and stats['worker_stopped']
    assert path.read_text() == 'previous frame'


def test_authenticated_control_origin_single_owner_and_timeout(tmp_path,monkeypatch):
    r=runtime_fixture(tmp_path,monkeypatch)
    app=create_app(r,'test-only-token')
    headers={'origin':'http://127.0.0.1:8790'}
    with TestClient(app) as client:
        assert client.get('/api/frame').status_code==401
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/control',headers={'origin':'https://untrusted.example'}):pass
        with client.websocket_connect('/control',headers=headers) as ws:
            ws.send_json({'token':'test-only-token'});status=ws.receive_json()
            for seq in range(4):
                time.sleep(.08)
                ws.send_json({'kind':'hold','held':False,'sequence':seq,'ticket':status['ticket']})
                status=ws.receive_json()
            with client.websocket_connect('/control',headers=headers) as second:
                second.send_json({'token':'test-only-token'})
                with pytest.raises(WebSocketDisconnect):second.receive_json()
            assert r.owner is not None
            page=client.get('/api/frame',headers={'Authorization':'Bearer test-only-token'}).json()
            assert client.get('/api/frame',headers={'Authorization':'Bearer test-only-token'}).headers['cache-control'] == 'no-store'
            ws.send_json({'kind':'select','sequence':4,'ticket':status['ticket'],
                          'event_id':page['event_id'],'u':.5,'v':.7})
            status=ws.receive_json()
            assert status['target'] is not None
            ws.send_json({'kind':'hold','held':False,'sequence':5,'ticket':status['ticket']})
            status=ws.receive_json()
            ws.send_json({'kind':'hold','held':True,'sequence':6,'ticket':status['ticket']})
            status=ws.receive_json()
            assert status['held']
            # Stalled tab cannot perpetuate motor authority using buffered packets.
            time.sleep(.4)
            with pytest.raises(WebSocketDisconnect):ws.receive_json()
        assert r.owner is None and not r.supervisor.held


@pytest.mark.parametrize('pitch,roll', [(10,0),(0,30),(-15,-20)])
def test_full_camera_pitch_roll_is_used_for_floor_intersection(pitch,roll):
    view,*_=camera()
    p,r=map(math.radians,(pitch,roll))
    rx=np.array([[1,0,0],[0,math.cos(p),-math.sin(p)],[0,math.sin(p),math.cos(p)]])
    rz=np.array([[math.cos(r),-math.sin(r),0],[math.sin(r),math.cos(r),0],[0,0,1]])
    matrix=np.eye(4);matrix[:3,:3]=rz@rx
    packet=view.packet.model_copy(update={'camera_transform':tuple(matrix.T.reshape(-1))})
    tilted=replace(view,packet=packet,event=view.event.model_copy(update={'pose':packet.pose}))
    target=(0.,-.10922,-.5)
    pixel=tilted.project(target)
    assert pixel is not None
    assert tilted.floor_target(*pixel,-.10922)==pytest.approx(target)


@pytest.mark.parametrize('height,yaw', [(0,0),(.10922,float('nan')),(float('inf'),0),(.10922,181),(True,0)])
def test_invalid_mount_calibration_refused(height,yaw):
    with pytest.raises(ValueError):PointSupervisor(height,yaw,started=0)


def test_writer_latest_pending_frame_wins_without_blocking_inference(tmp_path,monkeypatch):
    import threading
    entered,release=threading.Event(),threading.Event()
    original=cv2.imencode
    def slow(*args,**kwargs):
        entered.set();assert release.wait(3)
        return original(*args,**kwargs)
    monkeypatch.setattr(cv2,'imencode',slow)
    writer=PointPreviewWriter(tmp_path,INFO,'landscape_left')
    try:
        for seq in range(3):
            view,_,_,_,_,received=camera(seq,seq*.3)
            writer.last_submit=-float('inf')
            writer.submit(received,SimpleNamespace(event=view.event,image=np.full((480,640,3),120,np.uint8)))
            if seq==0:assert entered.wait(2)
        assert writer.dropped==1
        release.set()
        deadline=time.monotonic()+3
        while writer.written<2 and time.monotonic()<deadline:time.sleep(.01)
    finally:
        release.set();writer.close()
    assert json.loads((tmp_path/'point_frame.json').read_text())['event']['seq_id']==2


def test_server_flag_produces_exact_preview_through_replay_and_closes_writer(tmp_path):
    import subprocess
    import sys
    from tools.replay_client import Record, replay
    from vision.schema import encode
    from tests.test_server import wait_for
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    script='''from vision.pipeline import Pipeline, FrameResult
from vision.schema import ImageSize
class Fake:
    model_id='SYNTHETIC'; names={}; rules=[]; inactive_rules=[]
    def __call__(self,image):
        return FrameResult([],[],ImageSize(width=image.shape[1],height=image.shape[0]),0.,0,[])
Pipeline.from_config=classmethod(lambda cls,config:Fake())
from vision.server.__main__ import main
main()
'''
    log=tmp_path/'process.log'
    with log.open('w') as output:
        proc=subprocess.Popen([sys.executable,'-c',script,'--detect','--no-view','--point-preview',
            '--source-mode','REPLAY','--run-dir',str(tmp_path),'--host','127.0.0.1','--port',str(port)],
            stdout=output,stderr=subprocess.STDOUT)
        try:
            assert wait_for(lambda:'listening' in log.read_text() or proc.poll() is not None,timeout=15)
            assert proc.poll() is None,log.read_text()
            view,*_=camera()
            packet=view.packet
            asyncio.run(replay([Record(packet,JPEG,encode(packet,JPEG))],f'ws://127.0.0.1:{port}',speed=0))
            assert wait_for(lambda:(tmp_path/'point_frame.json').exists(),timeout=5),log.read_text()
        finally:
            proc.terminate()
            proc.wait(timeout=5)
    assert proc.returncode==0,log.read_text()
    info=json.loads((tmp_path/'run_info.json').read_text())
    data=json.loads((tmp_path/'point_frame.json').read_text())
    restored=CameraView.parse(data,info)
    assert restored.packet==packet and info['source_mode']=='REPLAY'
    assert restored.event.iphone_frame_ts_ns==packet.iphone_frame_ts_ns
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert summary['point_preview']['written']==1 and summary['point_preview']['worker_stopped']
