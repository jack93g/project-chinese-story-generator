import pytest

from story_generator.generation.providers.fake import FakeStoryGenerationProvider
from story_generator.generation.schemas import MAX_TARGET_WORD_COUNT
from story_generator.generation.worker import GenerationWorker
from story_generator.stories.persistence.models import Story
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


def test_create_returns_202_with_id_and_queued_status_without_calling_provider(
    client, db_session
):
    vocab_list = _make_list_with_items(db_session, skritter_list_id="post-1", n_items=3)

    response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert isinstance(body["id"], int)


def test_create_missing_list_id_returns_422(client):
    response = client.post(
        "/story-generations",
        json={
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 3,
        },
    )
    assert response.status_code == 422


def test_create_word_count_above_max_returns_422(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="post-wordcount", n_items=3
    )

    response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": MAX_TARGET_WORD_COUNT + 1,
            "target_vocabulary_count": 2,
        },
    )
    assert response.status_code == 422


def test_create_nonexistent_list_returns_404(client):
    response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": 999999,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )
    assert response.status_code == 404


def test_create_empty_list_returns_422(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="post-empty", n_items=0
    )

    response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )
    assert response.status_code == 422


def test_status_returns_404_for_unknown_id(client):
    response = client.get("/story-generations/999999")
    assert response.status_code == 404


def test_status_reveals_queued_state_before_processing(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="status-queued", n_items=2
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    response = client.get(f"/story-generations/{request_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["story_id"] is None
    assert body["error_code"] is None


def test_status_reveals_succeeded_state_and_story_id_after_worker_processes_it(
    client, db_session
):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="status-success", n_items=1
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    writing = vocab_list.items[0].writing
    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response=f'{{"title": "故事", "body": "这个故事里有{writing}。"}}',
    )
    worker = GenerationWorker(provider=provider)
    worker.run_once(db_session)
    db_session.commit()

    response = client.get(f"/story-generations/{request_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["story_id"] is not None
    assert body["error_code"] is None

    story = db_session.query(Story).filter_by(id=body["story_id"]).one()
    assert story.generation_request_id == request_id


def test_status_reveals_safe_error_message_for_diagnostic_failure(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="status-coverage-fail", n_items=1
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    provider = FakeStoryGenerationProvider(
        scenario="success",
        raw_response='{"title": "故事", "body": "完全无关的内容。"}',  # never uses the requested word
    )
    worker = GenerationWorker(provider=provider)
    worker.run_once(db_session)
    db_session.commit()

    response = client.get(f"/story-generations/{request_id}")

    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "InsufficientVocabularyCoverage"
    assert body["error_message"] is not None
    assert "coverage" in body["error_message"].lower()
    assert body["story_id"] is None


def test_status_collapses_provider_error_to_generic_safe_message(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="status-provider-fail", n_items=1
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    provider = FakeStoryGenerationProvider(scenario="api_error")
    worker = GenerationWorker(provider=provider)
    worker.run_once(db_session)
    db_session.commit()

    response = client.get(f"/story-generations/{request_id}")

    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "ProviderAPIError"
    # the raw provider message is NOT echoed verbatim — collapsed to
    # a generic safe message instead
    assert (
        body["error_message"] == "Story generation failed. You may retry this request."
    )


def test_retry_returns_404_for_unknown_id(client):
    response = client.post("/story-generations/999999/retry")
    assert response.status_code == 404


def test_retry_returns_409_when_request_is_not_in_a_failed_state(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="retry-not-failed", n_items=1
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    # still queued — never processed, so it's not eligible for retry
    response = client.post(f"/story-generations/{request_id}/retry")

    assert response.status_code == 409
    assert "not eligible for retry" in response.json()["detail"]


def test_retry_succeeds_for_an_eligible_failed_request(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="retry-eligible", n_items=1
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    provider = FakeStoryGenerationProvider(scenario="api_error")
    worker = GenerationWorker(provider=provider)
    worker.run_once(db_session)
    db_session.commit()

    response = client.post(f"/story-generations/{request_id}/retry")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"


def test_retry_returns_409_once_max_attempts_exhausted(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="retry-exhausted", n_items=1
    )
    create_response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 1,
        },
    )
    request_id = create_response.json()["id"]

    provider = FakeStoryGenerationProvider(scenario="api_error")
    worker = GenerationWorker(provider=provider)

    # Drive it through MAX_ATTEMPTS failure cycles: process, retry, repeat.
    from story_generator.generation.persistence.service import MAX_ATTEMPTS

    worker.run_once(db_session)
    db_session.commit()
    for _ in range(MAX_ATTEMPTS - 1):
        retry_response = client.post(f"/story-generations/{request_id}/retry")
        assert retry_response.status_code == 202
        worker.run_once(db_session)
        db_session.commit()

    # Now attempt_count == MAX_ATTEMPTS and status is 'failed' — next retry must be rejected.
    response = client.post(f"/story-generations/{request_id}/retry")

    assert response.status_code == 409


def _create(client, list_id):
    return client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": list_id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
        },
    )


def test_create_returns_429_once_active_requests_hit_the_cap(client, db_session):
    from story_generator.generation.persistence.service import MAX_ACTIVE_GENERATIONS

    vocab_list = _make_list_with_items(db_session, skritter_list_id="cap-1", n_items=3)

    for _ in range(MAX_ACTIVE_GENERATIONS):
        assert _create(client, vocab_list.id).status_code == 202

    assert _create(client, vocab_list.id).status_code == 429


def test_oversized_topic_returns_422(client, db_session):
    vocab_list = _make_list_with_items(
        db_session, skritter_list_id="topic-1", n_items=3
    )

    response = client.post(
        "/story-generations",
        json={
            "vocabulary_list_id": vocab_list.id,
            "target_hsk_level": 2,
            "target_word_count": 150,
            "target_vocabulary_count": 2,
            "topic": "x" * 201,
        },
    )

    assert response.status_code == 422
