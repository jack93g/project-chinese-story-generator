import pytest

from story_generator.generation.persistence.repository import (
    GenerationRequestRepository,
)
from story_generator.generation.persistence.service import (
    GenerationRequestService,
    VocabularyListNotFoundError,
)
from story_generator.generation.prompts.builder import CURRENT_PROMPT_VERSION
from story_generator.generation.schemas import CreateGenerationRequestSchema
from story_generator.generation.vocabulary_selection import EmptyVocabularyListError
from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList

pytestmark = pytest.mark.db


def _make_list_with_items(
    db_session, *, skritter_list_id: str, n_items: int
) -> VocabularyList:
    vocab_list = VocabularyList(skritter_list_id=skritter_list_id, name="Test list")
    db_session.add(vocab_list)
    db_session.flush()

    for i in range(n_items):
        item = VocabularyItem(
            skritter_vocab_id=f"{skritter_list_id}-item-{i}",
            language="zh",
            writing=f"词{i}",
            reading=f"ci{i}",
            definition_en=f"word {i}",
        )
        db_session.add(item)
        db_session.flush()
        vocab_list.items.append(item)

    db_session.flush()
    return vocab_list


def test_create_persists_request_with_prompt_version_and_snapshot(db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="create-1", n_items=5
    )
    repository = GenerationRequestRepository(db_session)
    service = GenerationRequestService(repository)

    payload = CreateGenerationRequestSchema(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=3,
        target_word_count=200,
        target_vocabulary_count=3,
        topic="office life",
    )

    request = service.create(db_session, payload)

    assert request.id is not None
    assert request.prompt_version == CURRENT_PROMPT_VERSION
    assert request.status == "queued"
    assert len(request.selected_vocabulary_snapshot) == 3


def test_create_resolves_provider_and_model_from_server_config_not_client(
    db_session, monkeypatch
):
    monkeypatch.setenv("OPENAI_PROVIDER_LABEL", "openrouter")
    monkeypatch.setenv("OPENAI_MODEL", "google/gemma-4-26b-a4b-it:free")

    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="create-provider", n_items=2
    )
    repository = GenerationRequestRepository(db_session)
    service = GenerationRequestService(repository)

    payload = CreateGenerationRequestSchema(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=1,
    )

    request = service.create(db_session, payload)

    assert request.provider == "openrouter"
    assert request.model == "google/gemma-4-26b-a4b-it:free"


def test_create_raises_on_missing_vocabulary_list(db_session):
    repository = GenerationRequestRepository(db_session)
    service = GenerationRequestService(repository)

    payload = CreateGenerationRequestSchema(
        vocabulary_list_id=999999,
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=1,
    )

    with pytest.raises(VocabularyListNotFoundError):
        service.create(db_session, payload)


def test_create_raises_on_empty_vocabulary_list(db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="create-empty", n_items=0
    )
    repository = GenerationRequestRepository(db_session)
    service = GenerationRequestService(repository)

    payload = CreateGenerationRequestSchema(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=1,
    )

    with pytest.raises(EmptyVocabularyListError):
        service.create(db_session, payload)


def test_create_caps_oversized_list_to_target_count(db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="create-oversized", n_items=20
    )
    repository = GenerationRequestRepository(db_session)
    service = GenerationRequestService(repository)

    payload = CreateGenerationRequestSchema(
        vocabulary_list_id=vocab_list.id,
        target_hsk_level=1,
        target_word_count=100,
        target_vocabulary_count=5,
    )

    request = service.create(db_session, payload)

    assert len(request.selected_vocabulary_snapshot) == 5
