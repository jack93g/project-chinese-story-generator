import httpx
import pytest
import respx

from story_generator.ingestion.persistence.models import (
    SyncRun,
    RawSkritterPayload,
)
from story_generator.vocabulary.persistence.models import (
    VocabularyItem,
    VocabularyList,
)
from story_generator.ingestion.persistence.repository import SyncRunRepository
from story_generator.ingestion.service import IngestionService
from story_generator.ingestion.skritter_client import SkritterClient
from story_generator.vocabulary.persistence.repository import VocabularyRepository


LIST_URL = "https://legacy.skritter.com/api/v0/vocablists/123"
VOCAB_URL = "https://legacy.skritter.com/api/v0/vocabs"


def _mock_successful_list(vocab_ids=("zh-你好-0",)):
    respx.get(LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "VocabList": {
                    "id": "123",
                    "name": "Test List",
                    "sections": [{"rows": [{"vocabId": v} for v in vocab_ids]}],
                }
            },
        )
    )


def _mock_vocab(vocab_id, writing, reading, definition):
    respx.get(VOCAB_URL, params={"ids": vocab_id}).mock(
        return_value=httpx.Response(
            200,
            json={
                "Vocabs": [
                    {
                        "id": vocab_id,
                        "language": "zh",
                        "writing": writing,
                        "reading": reading,
                        "definitions": {"en": definition},
                    }
                ]
            },
        )
    )


@pytest.mark.db
@respx.mock
def test_successful_sync_creates_succeeded_run_with_payloads(two_sessions):
    session, tracking_session = two_sessions

    _mock_successful_list(["zh-你好-0"])
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")

    client = SkritterClient("fake-token")
    vocabulary_repository = VocabularyRepository(session)
    sync_run_repository = SyncRunRepository(tracking_session)
    service = IngestionService(
        client, vocabulary_repository, session, sync_run_repository, tracking_session
    )

    result = service.run_single_list("123")
    assert result["vocab_imported"] == 1
    assert result["failures"] == []

    sync_run = tracking_session.query(SyncRun).one()
    assert sync_run.status == "succeeded"
    assert sync_run.completed_at is not None
    assert sync_run.summary["vocab_imported"] == 1

    payloads = (
        tracking_session.query(RawSkritterPayload)
        .filter_by(sync_run_id=sync_run.id)
        .all()
    )
    # one for the list fetch, one for the vocab fetch
    assert len(payloads) == 2
    assert {p.request_path for p in payloads} == {"/vocablists/123", "/vocabs"}

    # and the vocab actually landed in the database
    vocab = session.query(VocabularyItem).filter_by(skritter_vocab_id="zh-你好-0").one()
    assert vocab.writing == "你好"


@pytest.mark.db
@respx.mock
def test_failed_sync_marks_run_failed_and_rolls_back_vocab(two_sessions):
    session, tracking_session = two_sessions

    # list fetch succeeds, but the vocab fetch blows up mid-import
    _mock_successful_list(["zh-你好-0", "zh-谢谢-0"])
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")
    respx.get(VOCAB_URL, params={"ids": "zh-谢谢-0"}).mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    client = SkritterClient("fake-token")
    vocabulary_repository = VocabularyRepository(session)
    sync_run_repository = SyncRunRepository(tracking_session)
    service = IngestionService(
        client, vocabulary_repository, session, sync_run_repository, tracking_session
    )

    with pytest.raises(httpx.HTTPStatusError):
        service.run_single_list("123")

    sync_run = tracking_session.query(SyncRun).one()
    assert sync_run.status == "failed"
    assert sync_run.completed_at is not None
    assert sync_run.error_message is not None
    assert "HTTPStatusError" in sync_run.error_message

    # raw payloads recorded up to and including the failing call survive,
    # even though the import transaction rolled back
    payloads = (
        tracking_session.query(RawSkritterPayload)
        .filter_by(sync_run_id=sync_run.id)
        .all()
    )
    paths = [p.request_path for p in payloads]
    assert "/vocablists/123" in paths
    assert "/vocabs" in paths
    failing_payload = next(p for p in payloads if p.response_status == 500)
    assert failing_payload.payload == {"error": "boom"}

    # nothing from the failed business transaction was persisted:
    # neither vocab item made it in (first one was in-progress, uncommitted,
    # when the second call blew up and the whole session rolled back)
    assert session.query(VocabularyItem).count() == 0
    assert session.query(VocabularyList).count() == 0


@pytest.mark.db
@respx.mock
def test_reimporting_same_list_is_idempotent_and_creates_second_sync_run(two_sessions):
    session, tracking_session = two_sessions

    _mock_successful_list(["zh-你好-0"])
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")

    client = SkritterClient("fake-token")
    vocabulary_repository = VocabularyRepository(session)
    sync_run_repository = SyncRunRepository(tracking_session)
    service = IngestionService(
        client, vocabulary_repository, session, sync_run_repository, tracking_session
    )

    first = service.run_single_list("123")
    second = service.run_single_list("123")

    assert first["vocab_imported"] == 1
    assert first["vocab_skipped"] == 0

    assert second["vocab_imported"] == 0
    assert second["vocab_skipped"] == 1

    # exactly one vocab row and one list row exist despite two imports
    assert session.query(VocabularyItem).count() == 1
    assert session.query(VocabularyList).count() == 1

    # but two distinct SyncRun rows were created — each run is tracked separately
    sync_runs = tracking_session.query(SyncRun).all()
    assert len(sync_runs) == 2
    assert all(r.status == "succeeded" for r in sync_runs)
