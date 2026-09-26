from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.api.security import require_auth
from story_generator.auth.service import AuthenticatedUser
from story_generator.stories.persistence.repository import StoryRepository
from story_generator.stories.schemas import (
    FlagQuestionSchema,
    PaginatedStoryResponse,
    QuestionFlagResponse,
    QuizAttemptResponse,
    StoryDetail,
    SubmitQuizAttemptSchema,
)
from story_generator.stories.service import (
    InvalidQuestionIndexError,
    InvalidQuizAnswersError,
    StoryHasNoQuizError,
    StoryNotFoundError,
    StoryService,
)

router = APIRouter(tags=["stories"])


@router.get(
    "/stories",
    response_model=PaginatedStoryResponse,
)
def list_stories(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedStoryResponse:
    repository = StoryRepository(db)
    service = StoryService(repository)

    return service.list(limit=limit, offset=offset)


@router.get(
    "/stories/{story_id}",
    response_model=StoryDetail,
)
def get_story(
    story_id: int,
    db: Session = Depends(get_db),
) -> StoryDetail:
    repository = StoryRepository(db)
    service = StoryService(repository)

    try:
        return service.get(story_id)
    except StoryNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Story {story_id} not found"
        ) from exc


@router.delete(
    "/stories/{story_id}",
    status_code=204,
)
def delete_story(
    story_id: int,
    db: Session = Depends(get_db),
) -> None:
    repository = StoryRepository(db)
    service = StoryService(repository)

    try:
        service.delete(story_id)
    except StoryNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Story {story_id} not found"
        ) from exc

    db.commit()


@router.post(
    "/stories/{story_id}/quiz-attempts",
    response_model=QuizAttemptResponse,
    status_code=201,
)
def submit_quiz_attempt(
    story_id: int,
    payload: SubmitQuizAttemptSchema,
    db: Session = Depends(get_db),
    # Already run as the router's auth dependency; FastAPI reuses that
    # result here rather than checking again.
    user: AuthenticatedUser | None = Depends(require_auth),
) -> QuizAttemptResponse:
    repository = StoryRepository(db)
    service = StoryService(repository)

    try:
        attempt = service.submit_quiz_attempt(
            story_id, payload.answers, user_id=user.id if user else None
        )
    except StoryNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Story {story_id} not found"
        ) from exc
    except StoryHasNoQuizError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Story {story_id} has no comprehension questions",
        ) from exc
    except InvalidQuizAnswersError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    return attempt


@router.post(
    "/stories/{story_id}/question-flags",
    response_model=QuestionFlagResponse,
    status_code=201,
)
def flag_question(
    story_id: int,
    payload: FlagQuestionSchema,
    db: Session = Depends(get_db),
    # As for quiz attempts: the router's auth dependency, reused.
    user: AuthenticatedUser | None = Depends(require_auth),
) -> QuestionFlagResponse:
    repository = StoryRepository(db)
    service = StoryService(repository)

    try:
        flag = service.flag_question(
            story_id, payload.question_index, user_id=user.id if user else None
        )
    except StoryNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Story {story_id} not found"
        ) from exc
    except StoryHasNoQuizError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Story {story_id} has no comprehension questions",
        ) from exc
    except InvalidQuestionIndexError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    return flag
