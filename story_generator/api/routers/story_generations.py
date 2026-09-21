from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.api.rate_limit import generation_rate_limit
from story_generator.generation.persistence.repository import (
    GenerationRequestRepository,
)
from story_generator.generation.persistence.service import (
    GenerationQueueFullError,
    GenerationRequestNotFoundError,
    GenerationRequestService,
    InvalidTransitionError,
    RetryLimitExceededError,
    VocabularyListNotFoundError,
)
from story_generator.generation.schemas import (
    CreateGenerationRequestSchema,
    GenerationCreatedResponse,
    GenerationStatusResponse,
)
from story_generator.generation.vocabulary_selection import EmptyVocabularyListError

router = APIRouter(tags=["story-generations"])


@router.post(
    "/story-generations",
    response_model=GenerationCreatedResponse,
    status_code=202,
    dependencies=[Depends(generation_rate_limit)],
)
def create_story_generation(
    payload: CreateGenerationRequestSchema,
    db: Session = Depends(get_db),
) -> GenerationCreatedResponse:
    """
    Enqueues a story generation request. Returns immediately with the
    request id and 'queued' status — this endpoint never waits on an
    LLM call; the durable worker (story_generator.generation.worker)
    processes queued requests asynchronously.
    """
    repository = GenerationRequestRepository(db)
    service = GenerationRequestService(repository)

    try:
        request = service.create(db, payload)
    except VocabularyListNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmptyVocabularyListError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    db.commit()
    return GenerationCreatedResponse(id=request.id, status=request.status)


@router.get(
    "/story-generations/{generation_request_id}",
    response_model=GenerationStatusResponse,
)
def get_story_generation_status(
    generation_request_id: int,
    db: Session = Depends(get_db),
) -> GenerationStatusResponse:
    repository = GenerationRequestRepository(db)
    service = GenerationRequestService(repository)

    try:
        request = service._get(generation_request_id)
    except GenerationRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    story_id = repository.get_story_id_for_request(generation_request_id)
    return GenerationStatusResponse.from_request(request, story_id)


@router.post(
    "/story-generations/{generation_request_id}/retry",
    response_model=GenerationStatusResponse,
    status_code=202,
    dependencies=[Depends(generation_rate_limit)],
)
def retry_story_generation(
    generation_request_id: int,
    db: Session = Depends(get_db),
) -> GenerationStatusResponse:
    repository = GenerationRequestRepository(db)
    service = GenerationRequestService(repository)

    try:
        request = service.retry(generation_request_id)
    except GenerationRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GenerationQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RetryLimitExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Request {generation_request_id} is not eligible for retry "
                f"(current status: '{exc.current_status}')"
            ),
        ) from exc

    db.commit()
    story_id = repository.get_story_id_for_request(generation_request_id)
    return GenerationStatusResponse.from_request(request, story_id)
