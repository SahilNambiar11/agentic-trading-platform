from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db_session
from app.schemas.jobs import JobStage, JobStatus, PreviewJobResponse
from app.schemas.strategy import StrategyPreviewResponse
from app.services.job_store import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.get("/{job_id}", response_model=PreviewJobResponse)
def get_preview_job(
    job_id: UUID, current_user: CurrentUser, session: DatabaseSession
) -> PreviewJobResponse:
    job = get_job(session, job_id=job_id, user_id=current_user.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview job not found.")
    try:
        preview_result = (
            StrategyPreviewResponse.model_validate(job.preview_result)
            if job.status == "completed" and job.preview_result is not None
            else None
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This preview result has expired. Run the preview again.",
        ) from exc
    return PreviewJobResponse(
        id=job.id,
        status=cast(JobStatus, job.status),
        stage=cast(JobStage, job.stage),
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error_message,
        preview_result=preview_result,
    )
