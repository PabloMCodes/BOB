import hashlib
import io
import threading
from uuid import uuid4

import cv2
import numpy as np
import pytest

from tests.test_replay_detect import _frame
from tests.test_tape import CONFIG as TAPE, outline
from tests.test_zones import box
from tools.replay_detect import run
from vision.config import load_config
from vision.pipeline import FrameResult
from vision.scene import SceneInspector, SceneWriter
from vision.schema import ImageSize


class FakePipeline:
    model_id = "scene-test"
    rules = []
    calls = 0

    def __call__(self, image):
        self.calls += 1
        h,w=image.shape[:2]
        return FrameResult([box("person",(200.,30.,350.,320.)),box("foot",(260.,260.,295.,300.))],
                           [],ImageSize(width=w,height=h),1.,1,[])


def detections():
    first, second=uuid4(),uuid4()
    good=outline()
    bad=good.copy();cv2.rectangle(bad,(230,70),(300,150),(70,70,70),-1)
    records=[_frame(first,0,1_000_000_000,good,"portrait"),
             _frame(first,1,1_100_000_000,bad,"landscape_left"),
             _frame(second,0,1_200_000_000,good,"landscape_left")]
    found=[]
    pipeline=FakePipeline()
    run(records,pipeline,load_config(),on_frame=lambda o,d:found.append(d))
    assert pipeline.calls==3  # scene analysis does not invoke a detector a second time
    return found


def test_live_replay_semantics_and_exact_frame_correlation():
    inspector=SceneInspector(TAPE)
    found=detections()
    for d in found:
        live,a=inspector.inspect(d,"LIVE")
        replay,b=inspector.inspect(d,"REPLAY")
        assert a==b
        assert live['source_event_id']==str(d.event.event_id)
        assert live['session_id']==str(d.event.session_id)
        assert live['seq_id']==d.event.seq_id
        assert live['image_pixels_sha256']==hashlib.sha256(d.image.tobytes()).hexdigest()
        assert replay['source_mode']=='REPLAY'
        assert live['location_meaning']=='camera_observation_position'
    states=[inspector.inspect(d,'REPLAY')[1] for d in found]
    assert [s.region.status for s in states]==['recognized','unverified','recognized']
    assert states[0].people[0].status=='possible_person_in_zone'
    assert states[1].people[0].status=='unverified'


def test_retired_session_does_not_publish_active_boundary():
    from dataclasses import replace
    d=detections()[0]
    event=d.event.model_copy(update={'pose_valid':False,'pose':None,'pose_dt_ms':None,'pose_invalid_reason':'session_mismatch'})
    record,assessment=SceneInspector(TAPE).inspect(replace(d,event=event),'REPLAY')
    assert assessment.region.status=='unverified' and not assessment.region.polygon
    assert all(p.status=='unverified' for p in assessment.people)


def test_invalid_pose_keeps_image_observation_unlocalized():
    from dataclasses import replace
    d=detections()[0]
    event=d.event.model_copy(update={'pose_valid':False,'pose':None,'pose_dt_ms':None,'pose_invalid_reason':'tracking_not_normal'})
    record,assessment=SceneInspector(TAPE).inspect(replace(d,event=event),'REPLAY')
    assert record['observation_pose'] is None and record['location_meaning']=='unlocalized'
    assert assessment.region.status=='recognized'


def test_unknown_source_mode_rejected():
    with pytest.raises(ValueError):
        SceneInspector(TAPE).inspect(detections()[0],'pretend_live')


class BlockedStream(io.StringIO):
    def __init__(self):
        super().__init__();self.entered=threading.Event();self.release=threading.Event()

    def write(self,s):
        self.entered.set();self.release.wait(3)
        return super().write(s)


def test_slow_writer_is_bounded_and_shutdown_reports_pending():
    stream=BlockedStream();writer=SceneWriter(stream,capacity=1)
    writer.submit({'first':1});assert stream.entered.wait(1)
    for i in range(20):writer.submit({'n':i})
    stats=writer.close(timeout=.01)
    assert stats['dropped']==19 and stats['pending']==2 and stats['worker_running']
    stream.release.set();stats=writer.close()
    assert stats['written']==2 and stats['pending']==0 and not stats['worker_running']


def test_storage_failure_is_reported():
    class Broken(io.StringIO):
        def write(self,s):raise OSError('disk full')
    writer=SceneWriter(Broken());writer.submit({'x':1});stats=writer.close()
    assert stats['write_errors']==1 and stats['written']==0 and stats['last_error']=='disk full'
    with pytest.raises(RuntimeError):writer.submit({})
