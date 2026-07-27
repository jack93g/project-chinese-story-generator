from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.ingestion.persistence.repository import SyncRunRepository
from story_generator.ingestion.schemas import SyncStatusResponse
from story_generator.ingestion.service import SyncStatusService

router = APIRouter(tags=["sync-status"])


@router.get(
    "/sync-status",
    response_model=SyncStatusResponse,
)
def get_sync_status(
    db: Session = Depends(get_db),
) -> SyncStatusResponse:
    repository = SyncRunRepository(db)
    service = SyncStatusService(repository)

    return service.get_latest()