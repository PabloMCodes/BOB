"""Write schema/*.schema.json from vision/schema.py.

Run after any schema change:  uv run python -m tools.export_schema
tests/test_schema.py fails if the committed files drift from the code.
"""

import json
from pathlib import Path

from vision.schema import json_schemas

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for filename, schema in json_schemas().items():
        (SCHEMA_DIR / filename).write_text(render(schema))
        print(f"wrote schema/{filename}")


if __name__ == "__main__":
    main()
