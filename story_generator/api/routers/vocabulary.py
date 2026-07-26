from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.vocabulary.persistence.repository import VocabularyRepository
from story_generator.vocabulary.schemas import (
    PaginatedVocabularyListResponse,
    PaginatedVocabularyResponse,
    VocabularyListDetail,
)
from story_generator.vocabulary.service import (
    VocabularyListNotFoundError,
    VocabularyListService,
    VocabularyService,
)

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


@router.get(
    "/vocabulary-lists",
    response_model=PaginatedVocabularyListResponse,
)
def list_vocabulary_lists(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedVocabularyListResponse:
    repository = VocabularyRepository(db)
    service = VocabularyListService(repository)

    return service.list(limit=limit, offset=offset)


@router.get(
    "/vocabulary-lists/{list_id}",
    response_model=VocabularyListDetail,
)
def get_vocabulary_list(
    list_id: int,
    db: Session = Depends(get_db),
) -> VocabularyListDetail:
    repository = VocabularyRepository(db)
    service = VocabularyListService(repository)

    try:
        return service.get(list_id)
    except VocabularyListNotFoundError:
        raise HTTPException(status_code=404, detail=f"Vocabulary list {list_id} not found")