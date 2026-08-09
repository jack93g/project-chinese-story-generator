from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.generation.persistence.repository import GenerationRequestRepository
from story_generator.generation.persistence.service import GenerationRequestService, VocabularyListNotFoundError
from story_generator.generation.schemas import CreateGenerationRequestSchema, GenerationRequestDetail
from story_generator.generation.vocabulary_selection import EmptyVocabularyListError

router = APIRouter(tags=["generation-requests"])

# TODO(M3-6): per Codex review, the documented frontend contract is
# POST /story-generations returning 202 Accepted (async job pattern).
# This endpoint currently uses /generation-requests + 201 as a
# simpler synchronous stand-in for local development — align with the
# real contract when M3-6 implements the async flow.

@router.post(
    "/generation-requests",
    response_model=GenerationRequestDetail,
    status_code=201,
)
def create_generation_request(
    payload: CreateGenerationRequestSchema,
    db: Session = Depends(get_db),
) -> GenerationRequestDetail:
    repository = GenerationRequestRepository(db)
    service = GenerationRequestService(repository)

    try:
        request = service.create(db, payload)
    except VocabularyListNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EmptyVocabularyListError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db.commit()
    return request