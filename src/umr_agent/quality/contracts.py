from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from umr_agent.domain.models import StrictModel


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Finding(StrictModel):
    check: str
    severity: Severity
    message: str
    frame_indices: tuple[int, ...] = ()


class OutputInspection(StrictModel):
    """A file-contract report, not a judgment about motion quality."""

    npz_path: str
    keys: tuple[str, ...]
    frame_count: int | None = Field(default=None, ge=0)
    qpos_width: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0)
    findings: tuple[Finding, ...] = ()
    checks_not_run: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(f.severity == Severity.ERROR for f in self.findings)
