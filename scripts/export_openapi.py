"""Export the FastAPI OpenAPI schema to openapi.json at the repo root."""
import json
import pathlib

from monocle.main import app

out = pathlib.Path(__file__).parent.parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(f"Wrote {out}")
