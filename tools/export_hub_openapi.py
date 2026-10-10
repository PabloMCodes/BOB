"""Write schema/app/hub-openapi.json — the frontend's contract for the hub API (C10).

Run after any hub API change:  uv run python -m tools.export_hub_openapi
tests/test_hub_api.py fails if the committed file drifts from the code.
"""

import json
from pathlib import Path

from bobapp.hub.api import create_hub_app
from bobapp.hub.config import load_hub_config

OPENAPI_FILE = Path(__file__).resolve().parent.parent / "schema" / "app" / "hub-openapi.json"


def hub_openapi() -> dict:
    return create_hub_app(load_hub_config(), None, {}).openapi()


def main() -> None:
    OPENAPI_FILE.write_text(json.dumps(hub_openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OPENAPI_FILE.relative_to(OPENAPI_FILE.parents[2])}")


if __name__ == "__main__":
    main()
