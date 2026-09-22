"""Export the same schema served by FastAPI; no database or credentials required."""

import json
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
    destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"Exported API contract to {destination.name}")
