"""Read the vision server's local run identity; never infer LIVE from old logs."""
import json
from pathlib import Path
from uuid import UUID


def read_run_info(directory: Path):
    with (directory / "run_info.json").open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("run_info.json exceeds size limit")
    info = json.loads(data)
    if (not isinstance(info, dict) or info.get("run_info_version") != 1
            or info.get("producer") != "vision.server"
            or info.get("source_mode") not in {"LIVE", "REPLAY", "SAMPLE"}
            or type(info.get("started_ts_ns")) is not int or info["started_ts_ns"] <= 0):
        raise ValueError("invalid vision server run identity")
    UUID(info["run_id"])
    return info
