"""Start the local planning API with the token created by setup_local_token.py."""

import os
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    token_file = root / ".env.agent.local"
    if not token_file.is_file():
        raise SystemExit("Run 'uv run python scripts/setup_local_token.py' first.")
    allowed_keys = {"UMR_AGENT_API_TOKEN", "UMR_AGENT_WSL_DISTRO", "UMR_AGENT_WSL_ROOT", "UMR_AGENT_WSL_SCRIPT"}
    values = dict(
        line.split("=", 1)
        for line in token_file.read_text(encoding="utf-8").splitlines()
        if "=" in line and line.split("=", 1)[0] in allowed_keys
    )
    token = values.get("UMR_AGENT_API_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("Local API token is missing or too short. Run setup_local_token.py.")
    os.environ.update(values)
    uvicorn.run("umr_agent.api.app:app", host="127.0.0.1", port=8000, reload=True)
