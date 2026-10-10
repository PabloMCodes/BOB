"""Lane record envelope: the durable, deduplicated unit of the edge store and the sync link."""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import Field, model_validator

from .common import AppVersion, Lane, PosInt, RoverClock, SourceMode, _Model
from .control import EvidenceBody, GapBody, InspectionEndedBody, InspectionStartedBody, NoticeBody, ProfileRevisionBody
from .incident import IncidentBody
from .observation import ObservationBody
from .track import TrackPointBody

Body = Annotated[
    Union[ObservationBody, TrackPointBody, EvidenceBody, ProfileRevisionBody, InspectionStartedBody,
          InspectionEndedBody, IncidentBody, GapBody, NoticeBody],
    Field(discriminator="kind"),
]
BODY_LANE = {"observation": Lane.OBSERVATION, "track_point": Lane.TRACK}  # every other kind: control


class Record(_Model):
    """One durable lane record. `(edge_id, store_epoch, lane, seq)` is the deduplication key; order by
    `seq`, never by time."""
    app_version: AppVersion
    msg_type: Literal["record"]
    edge_id: str = Field(min_length=1)
    store_epoch: UUID
    lane: Lane
    seq: PosInt
    run_id: Optional[str] = None
    source_mode: SourceMode
    rover: RoverClock
    body: Body

    @model_validator(mode="after")
    def _lane(self) -> Record:
        if self.lane != BODY_LANE.get(self.body.kind, Lane.CONTROL):
            raise ValueError(f"a {self.body.kind} record does not belong in the {self.lane.value} lane")
        return self
