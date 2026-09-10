from story_generator.stories.persistence.repository import StoryRepository
from story_generator.stories.schemas import (
    PaginatedStoryResponse,
    StoryDetail,
    StorySummary,
)
from story_generator.vocabulary.schemas import VocabularyResponse


class StoryNotFoundError(Exception):
    def __init__(self, story_id: int):
        self.story_id = story_id
        super().__init__(f"Story {story_id} not found")


class StoryService:
    def __init__(self, repository: StoryRepository):
        self.repository = repository

    def list(self, limit: int, offset: int) -> PaginatedStoryResponse:
        stories = self.repository.list_page(limit=limit, offset=offset)
        total = self.repository.count()

        items = [
            StorySummary(
                id=story.id,
                title=story.title,
                created_at=story.created_at,
                target_hsk=story.target_hsk,
            )
            for story in stories
        ]

        return PaginatedStoryResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get(self, story_id: int) -> StoryDetail:
        story = self.repository.get_by_id(story_id)

        if story is None:
            raise StoryNotFoundError(story_id)

        return StoryDetail(
            id=story.id,
            title=story.title,
            created_at=story.created_at,
            target_hsk=story.target_hsk,
            content=story.content,
            selected_vocabulary=[
                VocabularyResponse(
                    id=item.id,
                    skritter_vocab_id=item.skritter_vocab_id,
                    language=item.language,
                    writing=item.writing,
                    reading=item.reading,
                    definition_en=item.definition_en,
                )
                for item in story.vocabulary_items
            ],
        )

    def delete(self, story_id: int) -> None:
        story = self.repository.get_by_id(story_id)

        if story is None:
            raise StoryNotFoundError(story_id)

        self.repository.delete(story)
