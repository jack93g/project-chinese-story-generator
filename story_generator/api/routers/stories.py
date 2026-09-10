from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from story_generator.api.dependencies import get_db
from story_generator.stories.persistence.repository import StoryRepository
from story_generator.stories.schemas import PaginatedStoryResponse, StoryDetail
from story_generator.stories.service import StoryNotFoundError, StoryService

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
    except StoryNotFoundError:
        raise HTTPException(status_code=404, detail=f"Story {story_id} not found")


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
    except StoryNotFoundError:
        raise HTTPException(status_code=404, detail=f"Story {story_id} not found")

    db.commit()
