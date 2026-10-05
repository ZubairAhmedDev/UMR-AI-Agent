from __future__ import annotations

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from umr_agent.agent.contracts import AgentCatalog, AgentReply, AgentRequest
from umr_agent.agent.diagnosis_loop import (
    DiagnosisReply,
    OllamaDiagnosisModel,
    RuleBasedDiagnosisModel,
    run_diagnosis,
)
from umr_agent.agent.improvement_service import (
    evaluate_improvement,
    prepare_improvement,
)
from umr_agent.agent.models import RuleBasedPlannerModel
from umr_agent.agent.providers.ollama import ModelUnavailable, OllamaPlannerModel
from umr_agent.agent.reviews import InputReview, ReviewRequest, build_input_review
from umr_agent.agent.service import AgentService
from umr_agent.api.wsl_assets import AssetStatus, check_assets
from umr_agent.api.wsl_attempts import (
    AttemptDiagnosis,
    AttemptRejected,
    AttemptStatus,
    PreparedAttempt,
    QueuedAttempt,
    read_attempt,
    write_attempt,
)

DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / "examples" / "catalog.example.json"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_path: Path = DEFAULT_CATALOG
    api_token: str | None = Field(default=None, min_length=32)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    wsl_distro: str | None = None
    wsl_root: str | None = None
    wsl_script: str | None = None

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            catalog_path=Path(os.getenv("UMR_AGENT_CATALOG", str(DEFAULT_CATALOG))),
            api_token=os.getenv("UMR_AGENT_API_TOKEN") or None,
            ollama_url=os.getenv("UMR_AGENT_OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("UMR_AGENT_OLLAMA_MODEL", "gemma3:4b"),
            wsl_distro=os.getenv("UMR_AGENT_WSL_DISTRO") or None,
            wsl_root=os.getenv("UMR_AGENT_WSL_ROOT") or None,
            wsl_script=os.getenv("UMR_AGENT_WSL_SCRIPT") or None,
        )


class ProposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    project_id: str = Field(default="project-umr-demo", min_length=1, max_length=100)
    actor: str = Field(default="local-user", min_length=1, max_length=200)
    provider: str = Field(default="rules", pattern="^(rules|ollama)$")


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(default="Explain the measured quality findings.", min_length=1, max_length=400)
    provider: str = Field(default="rules", pattern="^(rules|ollama)$")


class PrepareAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    motion_id: str = Field(pattern=r"^(spin-kick|run|speed-vault)$")
    max_frames: int = Field(default=3)
    profile: str = Field(
        default="baseline",
        pattern=r"^(baseline|ground-contact)$",
    )


class LaunchAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImprovementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    baseline_attempt: str
    candidate_attempt: str | None = None
    candidate_plan_hash: str | None = None
    reason: str


class DiagnosisScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    errors: int
    skating_frames: int
    velocity_warning_groups: int


class ImprovementEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    baseline_attempt: str
    candidate_attempt: str
    winner: str
    winner_attempt: str
    reason: str
    baseline: DiagnosisScoreResponse
    candidate: DiagnosisScoreResponse


def load_catalog(path: Path) -> AgentCatalog:
    with path.open("r", encoding="utf-8") as stream:
        return AgentCatalog.model_validate(json.load(stream))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_environment()
    app = FastAPI(title="UMR Agent API", version="0.2.0")

    def require_api_token(authorization: str | None = Header(default=None)) -> None:
        if config.api_token is None:
            raise HTTPException(status_code=503, detail="API token is not configured.")
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise HTTPException(status_code=401, detail="API token is required.")
        if not secrets.compare_digest(authorization[len(prefix) :], config.api_token):
            raise HTTPException(status_code=401, detail="Invalid API token.")

    def catalog_dependency() -> AgentCatalog:
        try:
            return load_catalog(config.catalog_path)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=503, detail="Agent catalog is unavailable.") from exc

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "component": "planning-api"}

    @app.get("/api/catalog", response_model=AgentCatalog, dependencies=[Depends(require_api_token)])
    def catalog(catalog_value: AgentCatalog = Depends(catalog_dependency)) -> AgentCatalog:  # noqa: B008
        return catalog_value

    @app.get("/api/assets/status", response_model=AssetStatus, dependencies=[Depends(require_api_token)])
    def asset_status() -> AssetStatus:
        return check_assets(config.wsl_distro, config.wsl_root, config.wsl_script)

    @app.get("/api/attempts/{attempt}/status", response_model=AttemptStatus,
             dependencies=[Depends(require_api_token)])
    def attempt_status(attempt: str) -> AttemptStatus:
        try:
            return read_attempt(config.wsl_distro, config.wsl_root, config.wsl_script,
                                attempt, "status")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/attempts/{attempt}/plan", response_model=PreparedAttempt,
             dependencies=[Depends(require_api_token)])
    def attempt_plan(attempt: str) -> PreparedAttempt:
        try:
            return read_attempt(config.wsl_distro, config.wsl_root, config.wsl_script,
                                attempt, "plan")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/attempts", response_model=PreparedAttempt,
              dependencies=[Depends(require_api_token)])
    def prepare_attempt(body: PrepareAttemptRequest) -> PreparedAttempt:
        try:
            return write_attempt(
                config.wsl_distro,
                config.wsl_root,
                config.wsl_script,
                "prepare",
                body.attempt,
                body.motion_id,
                body.max_frames,
                profile=body.profile,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AttemptRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/attempts/{attempt}/launch", response_model=QueuedAttempt,
              dependencies=[Depends(require_api_token)])
    def launch_attempt(attempt: str, body: LaunchAttemptRequest) -> QueuedAttempt:
        try:
            return write_attempt(config.wsl_distro, config.wsl_root, config.wsl_script,
                                 "launch", attempt, approved_hash=body.approved_plan_hash)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AttemptRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/attempts/{attempt}/diagnosis", response_model=AttemptDiagnosis,
             dependencies=[Depends(require_api_token)])
    def attempt_diagnosis(attempt: str) -> AttemptDiagnosis:
        try:
            return read_attempt(config.wsl_distro, config.wsl_root, config.wsl_script,
                                attempt, "diagnose")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/agent/attempts/{attempt}/improve",
        response_model=ImprovementResponse,
        dependencies=[Depends(require_api_token)],
    )
    def improve_attempt(attempt: str) -> ImprovementResponse:
        try:
            result = prepare_improvement(
                attempt,
                lambda name, action: read_attempt(
                    config.wsl_distro,
                    config.wsl_root,
                    config.wsl_script,
                    name,
                    action,
                ),
                lambda **kwargs: write_attempt(
                    config.wsl_distro,
                    config.wsl_root,
                    config.wsl_script,
                    **kwargs,
                ),
            )

            return ImprovementResponse(
                state=result.state,
                baseline_attempt=result.baseline_attempt,
                candidate_attempt=result.candidate_attempt,
                candidate_plan_hash=result.candidate_plan_hash,
                reason=result.reason,
            )

        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AttemptRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/agent/attempts/{attempt}/evaluate",
        response_model=ImprovementEvaluationResponse,
        dependencies=[Depends(require_api_token)],
    )
    def evaluate_attempt(attempt: str) -> ImprovementEvaluationResponse:
        try:
            result = evaluate_improvement(
                attempt,
                lambda name, action: read_attempt(
                    config.wsl_distro,
                    config.wsl_root,
                    config.wsl_script,
                    name,
                    action,
                ),
            )

            return ImprovementEvaluationResponse(
                state=result.state,
                baseline_attempt=result.baseline_attempt,
                candidate_attempt=result.candidate_attempt,
                winner=result.winner,
                winner_attempt=result.winner_attempt,
                reason=result.reason,
                baseline=DiagnosisScoreResponse(
                    errors=result.baseline.errors,
                    skating_frames=result.baseline.skating_frames,
                    velocity_warning_groups=result.baseline.velocity_warning_groups,
                ),
                candidate=DiagnosisScoreResponse(
                    errors=result.candidate.errors,
                    skating_frames=result.candidate.skating_frames,
                    velocity_warning_groups=result.candidate.velocity_warning_groups,
                ),
            )

        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/agent/attempts/{attempt}/analyze", response_model=DiagnosisReply,
              dependencies=[Depends(require_api_token)])
    def analyze_attempt(attempt: str, body: AnalyzeRequest) -> DiagnosisReply:
        model = (RuleBasedDiagnosisModel() if body.provider == "rules" else
                 OllamaDiagnosisModel(model=config.ollama_model, base_url=config.ollama_url))
        try:
            return run_diagnosis(
                attempt, body.goal, model,
                lambda name, action: read_attempt(config.wsl_distro, config.wsl_root,
                                                  config.wsl_script, name, action),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/api/agent/reviews", response_model=InputReview,
        dependencies=[Depends(require_api_token)],
    )
    def review(body: ReviewRequest) -> InputReview:
        if body.robot_id != "unitree-g1" or body.motion_id != "humanoid-spin-kick":
            raise HTTPException(status_code=409, detail="Only the G1 spin kick inputs can be reviewed.")
        status = check_assets(config.wsl_distro, config.wsl_root, config.wsl_script)
        try:
            return build_input_review(body, status)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/agent/proposals", response_model=AgentReply, dependencies=[Depends(require_api_token)]
    )
    def propose(
        body: ProposeRequest,
        catalog_value: AgentCatalog = Depends(catalog_dependency),  # noqa: B008
    ) -> AgentReply:
        model = (
            RuleBasedPlannerModel()
            if body.provider == "rules"
            else OllamaPlannerModel(model=config.ollama_model, base_url=config.ollama_url)
        )
        try:
            return AgentService(model, catalog_value).handle(
                AgentRequest(project_id=body.project_id, actor=body.actor, goal=body.goal)
            )
        except ModelUnavailable as exc:
            raise HTTPException(status_code=503, detail="Local Ollama model is unavailable.") from exc

    return app


app = create_app()
