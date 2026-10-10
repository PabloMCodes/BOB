"""Write schema/app/*.schema.json from bobapp/contracts.py (`bob-app` v1, C9/C10).

Run after any contract change:  uv run python -m tools.export_app_schema
tests/test_app_contracts.py fails if the committed files drift from the code.
"""

from pathlib import Path

from bobapp.contracts import app_json_schemas
from tools.export_schema import render

APP_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema" / "app"


def main() -> None:
    APP_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, schema in app_json_schemas().items():
        (APP_SCHEMA_DIR / filename).write_text(render(schema))
        print(f"wrote schema/app/{filename}")


if __name__ == "__main__":
    main()
