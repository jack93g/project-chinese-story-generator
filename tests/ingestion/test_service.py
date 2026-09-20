from unittest.mock import Mock

from story_generator.ingestion.service import IngestionService, SyncPartialFailureError


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
    repository.ensure_vocab.side_effect = [(10, True), (11, True)]

    service = IngestionService(client, repository, session, Mock(), Mock())
    result = service.import_list("123")

    assert result == {
        "lists_processed": 1,
        "vocab_processed": 2,
        "vocab_imported": 2,
        "vocab_skipped": 0,
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
    # first vocab is new, second already existed (conflict -> not inserted)
    repository.ensure_vocab.side_effect = [(10, True), (11, False)]

    service = IngestionService(client, repository, session, Mock(), Mock())
    result = service.import_list("123")

    assert result == {
        "lists_processed": 1,
        "vocab_processed": 2,
        "vocab_imported": 1,
        "vocab_skipped": 1,
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

    service = IngestionService(client, repository, session, Mock(), Mock())

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
    tracking_session = Mock()

    service = IngestionService(
        client, repository, session, tracking_repository, tracking_session
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
        client, repository, session, tracking_repository, tracking_session
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
    tracking_session = Mock()
    tracking_repository.create_sync_run.return_value = sync_run

    service = IngestionService(
        client, repository, session, tracking_repository, tracking_session
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
