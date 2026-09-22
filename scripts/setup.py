"""Create local Compose secrets without overwriting existing configuration."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; left unchanged.")
else:
    template = (root / ".env.example").read_text()
    template = template.replace("replace-with-random-url-safe-password", secrets.token_urlsafe(24))
    template = template.replace("replace-with-a-unique-secret-of-at-least-32-characters", secrets.token_urlsafe(48))
    target.write_text(template)
    print("Created .env with unique local secrets. Do not commit it.")
print("Start: docker compose --profile demo up --build -d")
print("Open: http://localhost:3000")
