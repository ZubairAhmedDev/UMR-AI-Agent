# API application

The first FastAPI service is implemented in `src/umr_agent/api/app.py`. Run it from the project
root with `uv run uvicorn umr_agent.api.app:app --reload --host 127.0.0.1 --port 8000`.

The current endpoints are `GET /api/health`, `GET /api/catalog`, and
`POST /api/agent/proposals`. They only inspect catalog entries and propose a motion request.
The actor field is a local demo label; authenticated identity and durable plans will be added
before job submission. No endpoint currently runs UMR.
