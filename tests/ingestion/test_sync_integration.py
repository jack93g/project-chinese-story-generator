import httpx
import pytest
import respx
from sqlalchemy.orm import sessionmaker

from story_generator.ingestion.persistence.models import (
    RawSkritterPayload,
    SyncRun,
)
from story_generator.ingestion.persistence.repository import (
    SyncLock,
    SyncRunRepository,
)
from story_generator.ingestion.service import (
    INTERRUPTED_RUN_MESSAGE,
    IngestionService,
    SyncAlreadyRunningError,
)
from story_generator.ingestion.skritter_client import SkritterClient
from story_generator.vocabulary.persistence.models import (
    VocabularyItem,
    VocabularyList,
)
from story_generator.vocabulary.persistence.repository import VocabularyRepository

LIST_URL = "https://legacy.skritter.com/api/v0/vocablists/123"
VOCAB_URL = "https://legacy.skritter.com/api/v0/vocabs"


@pytest.fixture
def lock_sessionmaker(engine):
    """Sessions for SyncLock, closed before two_sessions truncates."""
    sessions = []

    def make():
        session = sessionmaker(bind=engine)()
        sessions.append(session)
        return session

    yield make
    for session in sessions:
        session.close()


@pytest.fixture
def sync_lock(two_sessions, lock_sessionmaker):
    # Depends on two_sessions so it is torn down first.
    return SyncLock(lock_sessionmaker())


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
def test_successful_sync_creates_succeeded_run_with_payloads(two_sessions, sync_lock):
    session, tracking_session = two_sessions

    _mock_successful_list(["zh-你好-0"])
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")

    client = SkritterClient("fake-token")
    vocabulary_repository = VocabularyRepository(session)
    sync_run_repository = SyncRunRepository(tracking_session)
    service = IngestionService(
        client,
        vocabulary_repository,
        session,
        sync_run_repository,
        tracking_session,
        sync_lock=sync_lock,
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
def test_failed_sync_marks_run_failed_and_rolls_back_vocab(two_sessions, sync_lock):
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
        client,
        vocabulary_repository,
        session,
        sync_run_repository,
        tracking_session,
        sync_lock=sync_lock,
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
def test_reimporting_same_list_is_idempotent_and_creates_second_sync_run(
    two_sessions, sync_lock
):
    session, tracking_session = two_sessions

    _mock_successful_list(["zh-你好-0"])
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")

    client = SkritterClient("fake-token")
    vocabulary_repository = VocabularyRepository(session)
    sync_run_repository = SyncRunRepository(tracking_session)
    service = IngestionService(
        client,
        vocabulary_repository,
        session,
        sync_run_repository,
        tracking_session,
        sync_lock=sync_lock,
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


@pytest.mark.db
@respx.mock
def test_resync_does_not_refetch_known_vocab_unless_refreshing(two_sessions, sync_lock):
    session, tracking_session = two_sessions

    _mock_successful_list(["zh-你好-0"])
    vocab_route = respx.get(VOCAB_URL, params={"ids": "zh-你好-0"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "Vocabs": [
                    {
                        "id": "zh-你好-0",
                        "language": "zh",
                        "writing": "你好",
                        "reading": "ni3 hao3",
                        "definitions": {"en": "hello"},
                    }
                ]
            },
        )
    )

    def make_service(refresh):
        return IngestionService(
            SkritterClient("fake-token"),
            VocabularyRepository(session),
            session,
            SyncRunRepository(tracking_session),
            tracking_session,
            sync_lock=sync_lock,
            refresh=refresh,
        )

    make_service(refresh=False).run_single_list("123")
    second = make_service(refresh=False).run_single_list("123")
    assert vocab_route.call_count == 1
    assert second["vocab_fetched"] == 0

    third = make_service(refresh=True).run_single_list("123")
    assert vocab_route.call_count == 2
    assert third["vocab_fetched"] == 1
    assert third["vocab_skipped"] == 1


@pytest.mark.db
@respx.mock
def test_sync_is_refused_while_another_holds_the_lock(
    two_sessions, sync_lock, lock_sessionmaker
):
    session, tracking_session = two_sessions
    other_sync = SyncLock(lock_sessionmaker())
    assert other_sync.try_acquire()

    service = IngestionService(
        SkritterClient("fake-token"),
        VocabularyRepository(session),
        session,
        SyncRunRepository(tracking_session),
        tracking_session,
        sync_lock=sync_lock,
    )
    with pytest.raises(SyncAlreadyRunningError):
        service.run_single_list("123")
    assert tracking_session.query(SyncRun).count() == 0

    other_sync.release()
    _mock_successful_list([])
    service.run_single_list("123")
    assert tracking_session.query(SyncRun).one().status == "succeeded"


@pytest.mark.db
@respx.mock
def test_sync_marks_interrupted_runs_failed(two_sessions, sync_lock):
    session, tracking_session = two_sessions
    stale = SyncRun(status="running")
    tracking_session.add(stale)
    tracking_session.commit()

    _mock_successful_list([])
    IngestionService(
        SkritterClient("fake-token"),
        VocabularyRepository(session),
        session,
        SyncRunRepository(tracking_session),
        tracking_session,
        sync_lock=sync_lock,
    ).run_single_list("123")

    tracking_session.refresh(stale)
    assert stale.status == "failed"
    assert stale.error_message == INTERRUPTED_RUN_MESSAGE
    assert stale.completed_at is not None


@pytest.mark.db
@respx.mock
def test_sync_keeps_payloads_for_recent_runs_only(two_sessions, sync_lock, monkeypatch):
    session, tracking_session = two_sessions
    monkeypatch.setattr("story_generator.ingestion.service.RAW_PAYLOAD_RUNS_KEPT", 2)
    _mock_successful_list([])
    service = IngestionService(
        SkritterClient("fake-token"),
        VocabularyRepository(session),
        session,
        SyncRunRepository(tracking_session),
        tracking_session,
        sync_lock=sync_lock,
    )

    for _ in range(4):
        service.run_single_list("123")

    runs_with_payloads = {
        p.sync_run_id for p in tracking_session.query(RawSkritterPayload).all()
    }
    # the 2 newest runs before the last one started, plus the last one
    assert runs_with_payloads == {2, 3, 4}
    assert tracking_session.query(SyncRun).count() == 4


LISTS_URL = "https://legacy.skritter.com/api/v0/vocablists"


def _service(session, tracking_session, sync_lock):
    return IngestionService(
        SkritterClient("fake-token"),
        VocabularyRepository(session),
        session,
        SyncRunRepository(tracking_session),
        tracking_session,
        sync_lock=sync_lock,
    )


def _mock_list_index(*lists):
    return respx.get(LISTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"VocabLists": [{"id": i, "name": n} for i, n in lists]},
        )
    )


@pytest.mark.db
@respx.mock
def test_word_removed_in_skritter_is_unlinked_but_kept(two_sessions, sync_lock):
    session, tracking_session = two_sessions
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")
    _mock_vocab("zh-谢谢-0", "谢谢", "xie4 xie", "thanks")
    list_route = respx.get(LIST_URL)
    service = _service(session, tracking_session, sync_lock)

    _mock_successful_list(["zh-你好-0", "zh-谢谢-0"])
    service.run_single_list("123")

    _mock_successful_list(["zh-你好-0"])
    result = service.run_single_list("123")
    assert list_route.call_count == 2
    assert result["vocab_unlinked"] == 1

    vocab_list = session.query(VocabularyList).one()
    assert [item.writing for item in vocab_list.items] == ["你好"]
    # the word itself stays, so saved stories keep their glossary
    assert session.query(VocabularyItem).count() == 2


@pytest.mark.db
@respx.mock
def test_empty_list_response_keeps_existing_words(two_sessions, sync_lock):
    session, tracking_session = two_sessions
    _mock_vocab("zh-你好-0", "你好", "ni3 hao3", "hello")
    service = _service(session, tracking_session, sync_lock)

    _mock_successful_list(["zh-你好-0"])
    service.run_single_list("123")
    _mock_successful_list([])
    result = service.run_single_list("123")

    assert result["vocab_unlinked"] == 0
    assert len(session.query(VocabularyList).one().items) == 1


@pytest.mark.db
@respx.mock
def test_full_sync_archives_missing_lists_and_restores_returning_ones(
    two_sessions, sync_lock
):
    session, tracking_session = two_sessions
    _mock_successful_list([])
    respx.get(f"{LISTS_URL}/456").mock(
        return_value=httpx.Response(
            200,
            json={"VocabList": {"id": "456", "name": "Other", "sections": []}},
        )
    )
    service = _service(session, tracking_session, sync_lock)

    _mock_list_index(("123", "Test List"), ("456", "Other"))
    service.run_all_lists()

    _mock_list_index(("123", "Test List"))
    result = service.run_all_lists()
    assert result["lists_archived"] == 1
    other = session.query(VocabularyList).filter_by(skritter_list_id="456").one()
    assert other.archived_at is not None
    assert VocabularyRepository(session).count_lists() == 1

    # a later sync that only covers one list never archives anything
    _mock_list_index()
    service.run_single_list("123")
    session.refresh(other)
    assert other.archived_at is not None

    _mock_list_index(("123", "Test List"), ("456", "Other"))
    result = service.run_all_lists()
    assert result["lists_archived"] == 0
    session.refresh(other)
    assert other.archived_at is None
