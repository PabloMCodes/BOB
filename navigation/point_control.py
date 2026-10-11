"""Bounded point guidance with an expiring operator hold; no hardware IO."""
from dataclasses import replace
import math

from navigation.preview import Settings
from navigation.step import StepSettings, StepSupervisor


class PointSupervisor(StepSupervisor):
    def __init__(self, camera_height_m, yaw_offset_deg, *, started):
        if (type(camera_height_m) not in (int, float) or not math.isfinite(camera_height_m)
                or not .05 <= camera_height_m <= 1):
            raise ValueError('camera height must be measured, finite and within 0.05..1 m')
        if (type(yaw_offset_deg) not in (int, float) or not math.isfinite(yaw_offset_deg)
                or not -180 <= yaw_offset_deg <= 180):
            raise ValueError('forward yaw offset must be finite, within -180..180 degrees')
        super().__init__(StepSettings(seconds=120, max_steps=30, pulse_ms=100), started=started)
        self.preview.settings = Settings(stale_s=.5, mission_s=120, cell_m=.25, radius_cells=8)
        self.height, self.yaw_offset = camera_height_m, math.radians(yaw_offset_deg)
        self.target = self.target_session = self.floor_y = None
        self.arrived = False
        self.distance = self.heading_error = None
        self.held_until = -math.inf
        self.held = False
        self.release_required = True
        self.sequence = -1

    def revoke(self):
        self.held = False
        self.held_until = -math.inf
        self.release_required = True

    def clear_target(self):
        self.target = self.target_session = self.floor_y = None
        self.arrived = False
        self.distance = self.heading_error = None
        self.revoke()

    def select(self, view, u, v, now):
        self.revoke()
        self.target = self.target_session = None
        self.arrived = False
        self.distance = self.heading_error = None
        if not view.event.pose_valid or view.event.pose is None:
            raise ValueError("displayed frame has no valid pose")
        if self.active or self.fault or self.event is None or self.health is None:
            raise ValueError('wait until stopped with fresh camera observations')
        if self.decision.state != 'EXPLORE' or self.phase()[0] == 'COMPLETE':
            raise ValueError('target selection requires current normal camera observations')
        if (view.event.session_id != self.event.session_id
                or str(view.event.session_id) != self.decision.session_id
                or not 0 <= (self.wall-view.event.jetson_receive_ts_ns)/1e9 <= .5
                or not 0 <= now-self.mono <= .1):
            raise ValueError('displayed frame is stale or belongs to another session')
        floor = self.floor_y if self.floor_y is not None else view.event.pose.y_m-self.height
        target = view.floor_target(u, v, floor)
        self.target, self.target_session, self.floor_y = target, self.decision.session_id, floor
        self.arrived = False
        self.paused = 'target selected; release then hold the drive control'
        self._guide()

    def _guide(self):
        if not self.target or not self.event or not self.event.pose or self.decision.state != 'EXPLORE':
            return
        pose = self.event.pose
        dx, dz = self.target[0]-pose.x_m, self.target[2]-pose.z_m
        self.distance = math.hypot(dx, dz)
        desired = math.atan2(-dx, -dz)
        angle = desired - (pose.yaw_rad+self.yaw_offset)
        self.heading_error = math.atan2(math.sin(angle), math.cos(angle))
        self.arrived = self.distance <= .2
        direction = ('turn_left' if self.heading_error > 0 else 'turn_right') if abs(self.heading_error) > math.radians(12) else 'forward'
        self.decision = replace(self.decision, suggested_direction=None if self.arrived else direction)
        if self.arrived:
            self.revoke()

    def update(self, event, health, wall_ns, mono):
        super().update(event, health, wall_ns, mono)
        if self.decision.state in {'STOPPED', 'FAULT'} or (self.target_session and self.target_session != self.decision.session_id):
            self.clear_target()
        elif self.decision.state != 'EXPLORE':
            self.revoke()
        if self.held and mono >= self.held_until:
            self.revoke()
            self.pause('operator hold expired; release and press again')
        self._guide()
        return self.decision

    def phase(self):
        phase = super().phase()
        if phase[0] in {'FAULT', 'COMPLETE', 'PULSE'}:
            return phase
        if self.arrived:
            return 'ARRIVED', 'within 0.20 m of the camera-position target'
        if self.target is None:
            return 'NO_TARGET', 'select a nearby floor point'
        return phase

    def control(self, held, sequence, now):
        if type(held) is not bool or type(sequence) is not int or sequence <= self.sequence:
            self.revoke()
            raise ValueError('invalid or reordered operator control')
        self.sequence = sequence
        if not held:
            self.revoke()
            self.release_required = False
            return
        if self.held and now >= self.held_until:
            self.revoke()
        if self.release_required:
            return
        if not self.held:
            if self.target is None or not self.resume() or self.phase()[0] != 'READY':
                self.revoke()  # Holding while blocked is not queued for later.
                return
        if self.phase()[0] in {'FAULT', 'COMPLETE', 'ARRIVED', 'PAUSED', 'NO_TARGET', 'STOPPED', 'OBSERVE', 'HOLD', 'ANNOUNCE'}:
            self.revoke()
            return
        self.held = True
        self.held_until = now+.3

    def request(self):
        if not self.held or self.mono >= self.held_until or self.release_required:
            return None
        return super().request()

    def allowed(self, request, now, *, continuing=False):
        return (self.held and not self.release_required and now < self.held_until
                and super().allowed(request, now, continuing=continuing))
