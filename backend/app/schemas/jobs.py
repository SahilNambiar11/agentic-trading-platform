from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.strategy import StrategyPreviewResponse

JobStatus = Literal["queued", "running", "completed", "failed"]
JobStage = Literal[
    "queued",
    "parsing",
    "validating",
    "compiling",
    "loading_data",
    "backtesting",
    "generating_results",
    "completed",
    "failed",
]


class PreviewJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    status: JobStatus
    stage: JobStage
    progress: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None = None
    preview_result: StrategyPreviewResponse | None = None


class PreviewEnqueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    status: Literal["queued"] = "queued"
