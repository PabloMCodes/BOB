"""Pixel rays intersecting a measured horizontal floor. Advisory geometry only."""
from dataclasses import dataclass
import math

import numpy as np

from vision.schema import DetectionEvent, FramePacket
from vision.schema.pose import transform_matrix


@dataclass(frozen=True)
class CameraView:
    packet: FramePacket
    event: DetectionEvent
    orientation: str

    @classmethod
    def parse(cls, data, run_info):
        if not isinstance(data, dict) or data.get('version') != 1 or data.get('run_info') != run_info:
            raise ValueError('preview belongs to a different server run')
        packet = FramePacket.model_validate(data['packet'])
        event = DetectionEvent.model_validate(data['event'])
        if (packet.session_id != event.session_id or packet.seq_id != event.seq_id
                or packet.iphone_frame_ts_ns != event.iphone_frame_ts_ns
                or packet.tracking_state != event.tracking_state
                or event.jetson_receive_ts_ns < run_info['started_ts_ns']):
            raise ValueError('camera metadata does not match the displayed detection')
        if packet.intrinsics is None:
            raise ValueError('point preview needs source camera intrinsics')
        orientation = data['orientation']
        if orientation not in ('portrait', 'portrait_upside_down', 'landscape_left', 'landscape_right'):
            raise ValueError('unresolved image orientation')
        reported = packet.image.device_orientation.value
        if reported in ('portrait', 'portrait_upside_down', 'landscape_left', 'landscape_right') and reported != orientation:
            raise ValueError('resolved orientation conflicts with the source frame')
        w, h = packet.image.width, packet.image.height
        if orientation.startswith('portrait'):
            w, h = h, w
        if (event.image_size.width, event.image_size.height) != (w, h):
            raise ValueError('upright dimensions do not match camera metadata')
        if event.pose_valid and event.pose != packet.pose:
            raise ValueError('camera transform does not match detection pose')
        return cls(packet, event, orientation)

    def sensor_pixel(self, u, v):
        # Inputs are normalized upright image coordinates, excluding CSS letterboxing.
        if (type(u) not in (int, float) or type(v) not in (int, float)
                or not math.isfinite(u) or not math.isfinite(v) or not 0 <= u <= 1 or not 0 <= v <= 1):
            raise ValueError('click must be finite normalized image coordinates')
        x, y = u*(self.event.image_size.width-1), v*(self.event.image_size.height-1)
        w, h = self.packet.image.width, self.packet.image.height
        if self.orientation == 'portrait':
            return y, h-1-x
        if self.orientation == 'portrait_upside_down':
            return w-1-y, x
        if self.orientation == 'landscape_right':
            return w-1-x, h-1-y
        return x, y

    def intrinsics(self):
        k = self.packet.intrinsics
        if k is None:
            raise ValueError('camera intrinsics unavailable; no target estimate')
        sx, sy = self.packet.image.width/k.ref_width, self.packet.image.height/k.ref_height
        return k.fx*sx, k.fy*sy, k.cx*sx, k.cy*sy

    def floor_target(self, u, v, floor_y, max_distance=1.5):
        if not self.event.pose_valid or self.packet.tracking_state.value != 'normal':
            raise ValueError('valid normal-tracking camera pose required')
        x, y = self.sensor_pixel(u, v)
        fx, fy, cx, cy = self.intrinsics()
        matrix = transform_matrix(self.packet.camera_transform)
        origin = matrix[:3, 3]
        ray = matrix[:3, :3] @ np.array([(x-cx)/fx, -(y-cy)/fy, -1.])
        ray /= np.linalg.norm(ray)
        if not math.isfinite(floor_y) or origin[1] <= floor_y or ray[1] >= -math.sin(math.radians(8)):
            raise ValueError('select a nearby floor point clearly below the horizon')
        target = origin + ray*((floor_y-origin[1])/ray[1])
        distance = math.hypot(target[0]-origin[0], target[2]-origin[2])
        if not .2 < distance <= max_distance:
            raise ValueError(f'target distance must be greater than 0.20 m and at most {max_distance:.2f} m')
        return tuple(float(a) for a in target)

    def project(self, target):
        matrix = transform_matrix(self.packet.camera_transform)
        p = matrix[:3, :3].T @ (np.array(target)-matrix[:3, 3])
        if p[2] >= -.01:
            return None
        fx, fy, cx, cy = self.intrinsics()
        x, y = fx*p[0]/(-p[2])+cx, cy-fy*p[1]/(-p[2])
        w, h = self.packet.image.width, self.packet.image.height
        if self.orientation == 'portrait':
            x, y = h-1-y, x
        elif self.orientation == 'portrait_upside_down':
            x, y = y, w-1-x
        elif self.orientation == 'landscape_right':
            x, y = w-1-x, h-1-y
        u, v = x/max(1, self.event.image_size.width-1), y/max(1, self.event.image_size.height-1)
        return [float(u), float(v)] if 0 <= u <= 1 and 0 <= v <= 1 else None
