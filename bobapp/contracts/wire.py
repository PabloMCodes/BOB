"""Message union, the single parser and JSON Schema export (same role as vision/schema/wire.py)."""
from __future__ import annotations

from typing import Annotated, Union

from pydantic import BaseModel, Field, TypeAdapter

from .live import LiveState
from .profile import WorksiteProfile
from .record import Record
from .sync import BlobStatus, SyncAck, SyncBatch, SyncError, SyncHello, SyncLive, SyncWelcome

AppMessage = Annotated[
    Union[Record, LiveState, WorksiteProfile, SyncHello, SyncWelcome, SyncBatch, SyncAck, SyncLive,
          SyncError, BlobStatus],
    Field(discriminator="msg_type"),
]
APP_MESSAGE_MODELS = {m.model_fields["msg_type"].annotation.__args__[0]: m for m in
                      (Record, LiveState, WorksiteProfile, SyncHello, SyncWelcome, SyncBatch, SyncAck,
                       SyncLive, SyncError, BlobStatus)}
_ADAPTER: TypeAdapter = TypeAdapter(AppMessage)


def parse_app_message(data: Union[str, bytes, dict]) -> BaseModel:
    """The single parser for every `bob-app` envelope, whatever its source_mode."""
    if isinstance(data, dict):
        return _ADAPTER.validate_python(data)
    return _ADAPTER.validate_json(data)


def app_json_schemas() -> dict[str, dict]:
    return {f"{name}.schema.json": model.model_json_schema() for name, model in APP_MESSAGE_MODELS.items()}
