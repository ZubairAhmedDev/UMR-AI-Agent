"""Configure the same random local API token for FastAPI and Next.js."""

import os
import secrets
from pathlib import Path


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if line.split("=", 1)[0] not in updates]
    kept.extend(f"{key}={value}" for key, value in updates.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    token = secrets.token_urlsafe(32)
    update_env(root / ".env.agent.local", {"UMR_AGENT_API_TOKEN": token})
    update_env(
        root / "apps/web/.env.local",
        {
            "UMR_AGENT_API_TOKEN": token,
            "UMR_AGENT_API_URL": "http://127.0.0.1:8000",
        },
    )
    print("Local API token configured for both services. Restart FastAPI and Next.js.")
