from unittest.mock import Mock, patch

import pytest

from story_generator.ingestion.service import (
    RAW_PAYLOAD_RUNS_KEPT,
    IngestionService,
    SyncAlreadyRunningError,
    SyncPartialFailureError,
)


def test_import_list():
    client = Mock()
    repository = Mock()
    session = Mock()

    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": [
            "zh-你好-0",
            "zh-谢谢-0",
        ],
    }
    client.get_vocab.side_effect = [
        {
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
        {
            "Vocabs": [
                {
                    "id": "zh-谢谢-0",
                    "language": "zh",
                    "writing": "谢谢",
                    "reading": "xie4 xie",
                    "definitions": {"en": "thanks"},
                }
            ]
        },
    ]
    repository.ensure_list.return_value = 1
    repository.get_ids_by_skritter_vocab_ids.return_value = {}
    repository.unlink_vocab_not_in.return_value = 0
    repository.ensure_vocab.side_effect = [(10, True), (11, True)]

    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock()
    )
    result = service.import_list("123")

    assert result == {
        "lists_processed": 1,
        "vocab_processed": 2,
        "vocab_imported": 2,
        "vocab_skipped": 0,
        "vocab_fetched": 2,
        "vocab_unlinked": 0,
        "failures": [],
    }
    repository.ensure_list.assert_called_once_with("123", "Test List")
    assert repository.ensure_vocab.call_count == 2
    assert repository.link_vocab_to_list.call_count == 2
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_import_list_counts_skipped_vocab():
    client = Mock()
    repository = Mock()
    session = Mock()

    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": ["zh-你好-0", "zh-谢谢-0"],
    }
    client.get_vocab.side_effect = [
        {
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
        {
            "Vocabs": [
                {
                    "id": "zh-谢谢-0",
                    "language": "zh",
                    "writing": "谢谢",
                    "reading": "xie4 xie",
                    "definitions": {"en": "thanks"},
                }
            ]
        },
    ]
    repository.ensure_list.return_value = 1
    repository.get_ids_by_skritter_vocab_ids.return_value = {}
    repository.unlink_vocab_not_in.return_value = 0
    # first vocab is new, second already existed (conflict -> not inserted)
    repository.ensure_vocab.side_effect = [(10, True), (11, False)]

    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock()
    )
    result = service.import_list("123")

    assert result == {
        "lists_processed": 1,
        "vocab_processed": 2,
        "vocab_imported": 1,
        "vocab_skipped": 1,
        "vocab_fetched": 2,
        "vocab_unlinked": 0,
        "failures": [],
    }


def test_import_list_rolls_back_on_failure():
    client = Mock()
    repository = Mock()
    session = Mock()

    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": ["zh-你好-0"],
    }
    client.get_vocab.side_effect = RuntimeError("Skritter API failed")
    repository.get_ids_by_skritter_vocab_ids.return_value = {}
    repository.unlink_vocab_not_in.return_value = 0

    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock()
    )

    try:
        service.import_list("123")
        raise AssertionError("expected RuntimeError to propagate")
    except RuntimeError:
        pass

    session.commit.assert_not_called()
    session.rollback.assert_called_once()


# --- Sync tracking (run_single_list / run_all_lists) -----------------------


def _make_service_with_import_list(import_list_return):
    """Helper: a service whose import_list is stubbed directly, so these
    tests focus purely on the tracking wrapper's behavior, not the
    vocab-import internals (already covered above)."""
    client = Mock()
    repository = Mock()
    session = Mock()
    tracking_repository = Mock()
    tracking_repository.fail_interrupted_runs.return_value = 0
    tracking_session = Mock()

    service = IngestionService(
        client,
        repository,
        session,
        tracking_repository,
        tracking_session,
        sync_lock=Mock(),
    )
    service.import_list = Mock(side_effect=import_list_return)
    return service, client, tracking_repository, tracking_session


def test_run_single_list_marks_sync_run_succeeded():
    sync_run = Mock(id=42)
    success_result = {
        "lists_processed": 1,
        "vocab_processed": 2,
        "vocab_imported": 2,
        "vocab_skipped": 0,
        "failures": [],
    }
    service, client, tracking_repository, tracking_session = (
        _make_service_with_import_list([success_result])
    )
    tracking_repository.create_sync_run.return_value = sync_run

    result = service.run_single_list("123")

    assert result == success_result
    tracking_repository.create_sync_run.assert_called_once()
    tracking_repository.complete_sync_run.assert_called_once_with(42, success_result)
    tracking_repository.fail_sync_run.assert_not_called()
    assert tracking_session.commit.call_count == 2
    # on_response should be wired during the run and cleared afterward
    assert client.on_response is None


def test_run_single_list_marks_sync_run_failed_on_exception():
    sync_run = Mock(id=42)
    service, client, tracking_repository, tracking_session = (
        _make_service_with_import_list(RuntimeError("boom"))
    )
    tracking_repository.create_sync_run.return_value = sync_run

    try:
        service.run_single_list("123")
        raise AssertionError("expected RuntimeError to propagate")
    except RuntimeError:
        pass

    tracking_repository.complete_sync_run.assert_not_called()
    tracking_repository.fail_sync_run.assert_called_once()
    call_args = tracking_repository.fail_sync_run.call_args
    assert call_args.args[0] == 42
    assert "RuntimeError" in call_args.args[1]
    assert "boom" in call_args.args[1]
    assert call_args.kwargs.get("summary") is None
    assert tracking_session.commit.call_count == 2
    assert client.on_response is None


def test_run_all_lists_marks_sync_run_failed_on_partial_failure():
    sync_run = Mock(id=99)
    client = Mock()
    repository = Mock()
    session = Mock()
    tracking_repository = Mock()
    tracking_repository.fail_interrupted_runs.return_value = 0
    tracking_session = Mock()
    tracking_repository.create_sync_run.return_value = sync_run

    partial_result = {
        "lists_processed": 1,
        "vocab_processed": 2,
        "vocab_imported": 2,
        "vocab_skipped": 0,
        "failures": [{"id": "456", "name": "Broken List", "error": "boom"}],
    }

    service = IngestionService(
        client,
        repository,
        session,
        tracking_repository,
        tracking_session,
        sync_lock=Mock(),
    )
    service.import_all_lists = Mock(return_value=partial_result)

    try:
        service.run_all_lists()
        raise AssertionError("expected SyncPartialFailureError to propagate")
    except SyncPartialFailureError:
        pass

    tracking_repository.complete_sync_run.assert_not_called()
    tracking_repository.fail_sync_run.assert_called_once()
    call_args = tracking_repository.fail_sync_run.call_args
    assert call_args.args[0] == 99
    assert "Broken List" in call_args.args[1]
    # summary is preserved even though the run is marked failed
    assert call_args.kwargs.get("summary") == partial_result
    assert tracking_session.commit.call_count == 2


def test_run_single_list_wires_raw_payload_recording():
    sync_run = Mock(id=7)
    client = Mock()
    repository = Mock()
    session = Mock()
    tracking_repository = Mock()
    tracking_repository.fail_interrupted_runs.return_value = 0
    tracking_session = Mock()
    tracking_repository.create_sync_run.return_value = sync_run

    service = IngestionService(
        client,
        repository,
        session,
        tracking_repository,
        tracking_session,
        sync_lock=Mock(),
    )

    captured_recorder = {}

    def fake_import_list(list_id):
        # capture on_response as it exists mid-run, before the finally clears it
        captured_recorder["fn"] = client.on_response
        return {
            "lists_processed": 1,
            "vocab_processed": 0,
            "vocab_imported": 0,
            "vocab_skipped": 0,
            "failures": [],
        }

    service.import_list = Mock(side_effect=fake_import_list)

    service.run_single_list("123")

    assert captured_recorder["fn"] is not None
    # simulate the client invoking the recorder as it would for a real response
    captured_recorder["fn"]("/vocabs", {"ids": "x"}, 200, {"Vocabs": []})
    tracking_repository.add_raw_payload.assert_called_once_with(
        7, "/vocabs", {"ids": "x"}, 200, {"Vocabs": []}
    )
    assert tracking_session.commit.call_count == 3


def test_import_list_links_known_vocab_without_fetching_it():
    client = Mock()
    repository = Mock()
    session = Mock()

    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": ["zh-你好-0", "zh-谢谢-0", "zh-你好-0"],
    }
    client.get_vocab.return_value = {
        "Vocabs": [
            {
                "id": "zh-谢谢-0",
                "language": "zh",
                "writing": "谢谢",
                "reading": "xie4 xie",
                "definitions": {"en": "thanks"},
            }
        ]
    }
    repository.ensure_list.return_value = 1
    repository.get_ids_by_skritter_vocab_ids.return_value = {"zh-你好-0": 10}
    repository.unlink_vocab_not_in.return_value = 0
    repository.ensure_vocab.return_value = (11, True)

    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock()
    )
    result = service.import_list("123")

    client.get_vocab.assert_called_once_with("zh-谢谢-0")
    repository.get_ids_by_skritter_vocab_ids.assert_called_once_with(
        ["zh-你好-0", "zh-谢谢-0"]
    )
    assert repository.link_vocab_to_list.call_args_list == [
        ((1, 10),),
        ((1, 11),),
    ]
    assert result["vocab_imported"] == 1
    assert result["vocab_skipped"] == 1
    assert result["vocab_fetched"] == 1


def test_import_list_with_refresh_fetches_every_word():
    client = Mock()
    repository = Mock()
    session = Mock()

    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": ["zh-你好-0"],
    }
    client.get_vocab.return_value = {
        "Vocabs": [
            {
                "id": "zh-你好-0",
                "language": "zh",
                "writing": "你好",
                "reading": "ni3 hao3",
                "definitions": {"en": "hello"},
            }
        ]
    }
    repository.ensure_list.return_value = 1
    repository.ensure_vocab.return_value = (10, False)
    repository.unlink_vocab_not_in.return_value = 0

    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock(), refresh=True
    )
    result = service.import_list("123")

    repository.get_ids_by_skritter_vocab_ids.assert_not_called()
    client.get_vocab.assert_called_once_with("zh-你好-0")
    assert result["vocab_skipped"] == 1
    assert result["vocab_fetched"] == 1


def test_run_raises_and_records_nothing_when_lock_is_held():
    sync_lock = Mock()
    sync_lock.try_acquire.return_value = False
    tracking_repository = Mock()
    service = IngestionService(
        Mock(), Mock(), Mock(), tracking_repository, Mock(), sync_lock=sync_lock
    )

    with pytest.raises(SyncAlreadyRunningError):
        service.run_all_lists()

    tracking_repository.create_sync_run.assert_not_called()
    tracking_repository.fail_interrupted_runs.assert_not_called()
    sync_lock.release.assert_not_called()


def test_run_releases_lock_even_when_sync_fails():
    service, _, tracking_repository, _ = _make_service_with_import_list(
        RuntimeError("boom")
    )
    tracking_repository.create_sync_run.return_value = Mock(id=1)

    with pytest.raises(RuntimeError):
        service.run_single_list("123")

    service.sync_lock.release.assert_called_once()


def test_run_cleans_up_before_creating_the_new_run():
    service, _, tracking_repository, _ = _make_service_with_import_list(
        [
            {
                "lists_processed": 1,
                "vocab_processed": 0,
                "vocab_imported": 0,
                "vocab_skipped": 0,
                "vocab_fetched": 0,
                "failures": [],
            }
        ]
    )
    tracking_repository.create_sync_run.return_value = Mock(id=1)

    service.run_single_list("123")

    names = [c[0] for c in tracking_repository.method_calls]
    assert names.index("fail_interrupted_runs") < names.index("create_sync_run")
    tracking_repository.prune_raw_payloads.assert_called_once_with(
        keep_runs=RAW_PAYLOAD_RUNS_KEPT
    )


def _list_import_service(vocab_ids, known, fetched_db_id=None):
    client = Mock()
    repository = Mock()
    client.get_list.return_value = {
        "id": "123",
        "name": "Test List",
        "vocab_ids": vocab_ids,
    }
    client.get_vocab.return_value = {
        "Vocabs": [
            {
                "id": "zh-谢谢-0",
                "language": "zh",
                "writing": "谢谢",
                "reading": "xie4 xie",
                "definitions": {"en": "thanks"},
            }
        ]
    }
    repository.ensure_list.return_value = 1
    repository.get_ids_by_skritter_vocab_ids.return_value = known
    repository.ensure_vocab.return_value = (fetched_db_id, True)
    session = Mock()
    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock()
    )
    return service, repository, session


def test_import_list_unlinks_words_no_longer_in_the_list():
    service, repository, session = _list_import_service(
        ["zh-你好-0", "zh-谢谢-0"], known={"zh-你好-0": 10}, fetched_db_id=11
    )
    repository.unlink_vocab_not_in.return_value = 3

    result = service.import_list("123")

    repository.unlink_vocab_not_in.assert_called_once_with(1, {10, 11})
    assert result["vocab_unlinked"] == 3
    session.commit.assert_called_once()


# Patch the logger rather than use caplog: Alembic's fileConfig, run by the
# migration tests, disables loggers that already exist.
def test_import_list_keeps_words_when_skritter_returns_an_empty_list():
    service, repository, session = _list_import_service([], known={})
    repository.count_list_items.return_value = 5

    with patch("story_generator.ingestion.service.logger") as logger:
        result = service.import_list("123")

    repository.unlink_vocab_not_in.assert_not_called()
    assert result["vocab_unlinked"] == 0
    assert "keeping them" in logger.warning.call_args.args[0]
    session.commit.assert_called_once()


def _all_lists_service(lists):
    client = Mock()
    repository = Mock()
    session = Mock()
    client.get_lists.return_value = lists
    service = IngestionService(
        client, repository, session, Mock(), Mock(), sync_lock=Mock()
    )
    service.import_list = Mock(
        return_value={
            "lists_processed": 1,
            "vocab_processed": 0,
            "vocab_imported": 0,
            "vocab_skipped": 0,
            "vocab_fetched": 0,
            "vocab_unlinked": 0,
            "failures": [],
        }
    )
    return service, repository, session


def test_import_all_lists_archives_lists_skritter_no_longer_returns():
    service, repository, session = _all_lists_service(
        [{"id": "1", "name": "One"}, {"id": "2", "name": "Two"}]
    )
    repository.archive_lists_not_in.return_value = ["Old list"]

    result = service.import_all_lists()

    repository.archive_lists_not_in.assert_called_once_with({"1", "2"})
    assert result["lists_archived"] == 1
    session.commit.assert_called_once()


def test_import_all_lists_archives_nothing_when_skritter_returns_no_lists():
    service, repository, _ = _all_lists_service([])
    repository.count_lists.return_value = 4

    with patch("story_generator.ingestion.service.logger") as logger:
        result = service.import_all_lists()

    repository.archive_lists_not_in.assert_not_called()
    assert result["lists_archived"] == 0
    logger.warning.assert_called_once_with("Skritter returned no lists; archiving none")
