from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.vocabulary.persistence.repository import VocabularyRepository
from story_generator.vocabulary.schemas import PaginatedVocabularyResponse
from story_generator.vocabulary.service import VocabularyService

router = APIRouter(tags=["vocabulary"])


@router.get(
    "/vocabulary",
    response_model=PaginatedVocabularyResponse,
)
def list_vocabulary(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedVocabularyResponse:
    repository = VocabularyRepository(db)
    service = VocabularyService(repository)

    return service.list(limit=limit, offset=offset)
