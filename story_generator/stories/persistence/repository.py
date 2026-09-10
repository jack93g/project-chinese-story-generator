from sqlalchemy.orm import Session

from story_generator.stories.persistence.models import Story


class StoryRepository:
    """Persistence operations for stories.

    Transaction boundaries are controlled by the calling service.
    """

    def __init__(self, session: Session):
        self.session = session

    def list_page(self, limit: int, offset: int) -> list[Story]:
        return (
            self.session.query(Story)
            .order_by(Story.id.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count(self) -> int:
        return self.session.query(Story).count()

    def get_by_id(self, story_id: int) -> Story | None:
        return self.session.get(Story, story_id)

    def delete(self, story: Story) -> None:
        self.session.delete(story)
