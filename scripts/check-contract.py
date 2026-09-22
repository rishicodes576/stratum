"""Compare semantic JSON; formatting differs between Python and Prettier."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
committed = subprocess.check_output(
    ["git", "show", "HEAD:frontend/openapi.json"], cwd=root, text=True
)
actual = (root / "frontend/openapi.json").read_text()
if json.loads(committed) != json.loads(actual):
    raise SystemExit("API schema changed. Export OpenAPI and run npm run generate:api before committing.")
print("Committed OpenAPI contract matches FastAPI.")
