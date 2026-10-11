"""General scene selection remains independent of PPE, storage and sync ordering."""
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from bobapp.contracts import Delivery, Lane, Record
from bobapp.edge.config import load_edge_config
from bobapp.edge.publish.site_photos import SitePhotoSelector, SitePhotoSettings
from bobapp.edge.store import EdgeStore
from bobapp.hub.api import create_hub_app
from bobapp.hub.config import load_hub_config
from bobapp.hub.replica import Replica
from tests.test_offline_frames import detection, publisher
from vision.schema import ImageSize, Pose

SESSION = uuid4()


def frame(t=0, x=0, yaw=0, seed=1, session=SESSION, valid=True):
    d = detection(int(t * 10))
    d.image = np.random.default_rng(seed).integers(30, 220, (240, 320, 3), dtype=np.uint8)
    d.event = d.event.model_copy(update={
        'session_id': session, 'iphone_frame_ts_ns': int((t + 1) * 1e9),
        'image_size': ImageSize(width=320, height=240),
        'pose': Pose(x_m=x, y_m=0, z_m=0, yaw_rad=yaw) if valid else None,
        'pose_valid': valid, 'pose_invalid_reason': None if valid else 'no_pose',
        'pose_dt_ms': 0 if valid else None,
    })
    return d


def select(selector, d):
    candidate = selector.offer(d.event, d.image)
    if candidate:
        selector.commit(candidate)
    return candidate


def test_stationary_duplicate_timeout_does_not_force_photo():
    s = SitePhotoSelector(SitePhotoSettings())
    assert select(s, frame())
    for t in (1, 3, 30, 90):
        assert select(s, frame(t)) is None
    assert s.counts['selected'] == 1
    assert s.counts['duplicate_rejected'] == 2


def test_new_viewpoint_and_turn_allow_overlap_even_in_similar_rooms():
    s = SitePhotoSelector(SitePhotoSettings())
    assert select(s, frame())
    assert select(s, frame(3, x=1)).details['reason'] == 'new_viewpoint'
    assert select(s, frame(6, x=1, yaw=1))
    assert select(s, frame(9)) is None  # revisit the original view


def test_changed_scene_without_pose_and_quality_filters():
    s = SitePhotoSelector(SitePhotoSettings())
    assert select(s, frame(valid=False))
    changed = frame(30, valid=False)
    changed.image[:, :160] = 30
    assert select(s, changed).details['reason'] == 'changed_view'
    for t, value in ((60, 0), (90, 255), (120, 120)):
        d = frame(t, valid=False)
        d.image[:] = value
        assert select(s, d) is None
    assert s.counts['quality_rejected'] == 3


def test_session_reset_monotonic_frames_bounded_memory_and_commit_only():
    s = SitePhotoSelector(SitePhotoSettings(history_size=2))
    d = frame()
    assert s.offer(d.event, d.image) is not None
    assert len(s.history) == 0  # unsaved candidate cannot suppress future photos
    assert select(s, frame(3))
    assert select(s, frame(2)) is None
    assert select(s, frame(6, x=1))
    assert select(s, frame(9, x=2))
    assert len(s.history) == 2
    assert select(s, frame(session=uuid4()))
    assert len(s.history) == 1


@pytest.mark.parametrize('kwargs', [dict(enabled='yes'), dict(history_size=0), dict(history_size=True),
    dict(min_interval_s=0), dict(min_move_m=float('nan')), dict(min_turn_deg=181),
    dict(similarity_threshold=2), dict(max_brightness=10), dict(max_interval_s=1)])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        SitePhotoSettings(**kwargs)


def test_saved_selection_syncs_without_people_and_late_notice_is_visible(tmp_path):
    store = EdgeStore(tmp_path / 'edge', 'test')
    config = load_edge_config()
    config['archive']['enabled'] = False
    p = publisher(store, config)
    inputs = [frame(), frame(3), frame(6, x=1)]
    for d in inputs:
        p.on_detection(d)
    stats = p.close(10)
    assert stats['write_errors'] == 0, stats
    assert stats['archived_frames'] == 2
    observations = [Record.model_validate_json(r.json) for r in store.read(Lane.OBSERVATION, 0)]
    notices = [Record.model_validate_json(r.json) for r in store.read(Lane.CONTROL, 0)]
    selected = [r for r in notices if r.body.kind == 'notice' and r.body.code == 'site_photo']
    assert len(selected) == 2
    for record, d in zip(observations, inputs):
        assert record.body.event.model_dump(mode='json') == d.event.model_dump(mode='json')
    r = Replica(tmp_path / 'hub')
    ws, _ = r.adopt(store.edge_id, store.store_epoch)
    r.commit(ws, Lane.OBSERVATION, observations, Delivery.BACKFILLED)
    app = create_hub_app(load_hub_config(), None, {'rover': tmp_path / 'hub'})
    with TestClient(app) as client:
        assert len(client.get('/v1/frames').json()['items']) == 2
        assert client.get('/v1/frames?site_only=true').json()['items'] == []
        r.commit(ws, Lane.CONTROL, notices, Delivery.BACKFILLED)
        items = client.get('/v1/frames?site_only=true').json()['items']
        assert len(items) == 2
        assert all(i['image_status'] == 'pending_sync' for i in items)
        for item in items:
            sha = item['record']['body']['evidence_sha256']
            assert item['site_photo']['evidence_sha256'] == sha
            r.store_blob(sha, store.blob_file(sha).read_bytes())
        assert all(i['image_status'] == 'available' for i in client.get('/v1/frames?site_only=true').json()['items'])
        first = client.get('/v1/frames?site_only=true&latest=false&limit=1').json()
        second = client.get(f"/v1/frames?site_only=true&latest=false&after={first['next_after']}").json()
        assert len(second['items']) == 1
    r.close()
    store.close()


def test_storage_pressure_does_not_mark_selection_saved(tmp_path):
    store = EdgeStore(tmp_path / 'edge', 'test')
    config = load_edge_config()
    config['retention']['max_store_bytes'] = 1
    p = publisher(store, config)
    p.on_detection(frame())
    stats = p.close(10)
    assert stats['archived_frames'] == 0
    assert p.site_photos.counts['selected'] == 0
    notices = [Record.model_validate_json(r.json).body for r in store.read(Lane.CONTROL, 0)]
    assert not any(b.kind == 'notice' and b.code == 'site_photo' for b in notices)
    store.close()
