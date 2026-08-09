import pytest

from story_generator.generation.schemas import MAX_TARGET_WORD_COUNT
from story_generator.vocabulary.persistence.models import VocabularyItem, VocabularyList

pytestmark = pytest.mark.db


def _make_list_with_items(db_session, *, skritter_list_id: str, n_items: int) -> VocabularyList:
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


def test_create_generation_request_success(client, db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="router-1", n_items=5)

    response = client.post(
        "/generation-requests",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 3,
            "topic": "office life",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["prompt_version"] == "story-v1"
    assert len(body["selected_vocabulary_snapshot"]) == 3


def test_create_generation_request_missing_list_id_returns_422(client):
    response = client.post(
        "/generation-requests",
        json={"target_hsk_level": 2, "target_word_count": 150, "target_vocabulary_count": 3},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("hsk_level", [0, 7])
def test_create_generation_request_invalid_hsk_level_returns_422(client, db_session, hsk_level):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="router-hsk", n_items=3)

    response = client.post(
        "/generation-requests",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": hsk_level,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )

    assert response.status_code == 422


def test_create_generation_request_word_count_above_max_returns_422(client, db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="router-wordcount", n_items=3)

    response = client.post(
        "/generation-requests",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": MAX_TARGET_WORD_COUNT + 1,
            "target_vocabulary_count": 2,
        },
    )

    assert response.status_code == 422


def test_create_generation_request_nonexistent_list_returns_404(client):
    response = client.post(
        "/generation-requests",
        json={
            "vocabulary_list_id": 999999,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )

    assert response.status_code == 404


def test_create_generation_request_empty_list_returns_422(client, db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="router-empty", n_items=0)

    response = client.post(
        "/generation-requests",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )

    assert response.status_code == 422


def test_create_generation_request_does_not_persist_client_supplied_provider(client, db_session):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="router-provider", n_items=2)

    response = client.post(
        "/generation-requests",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
            "provider": "malicious-provider",
            "model": "malicious-model",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] != "malicious-provider"
    assert body["model"] != "malicious-model"