from unittest.mock import Mock

import pytest

from story_generator.cli import ingestion as cli
from story_generator.ingestion.service import SyncAlreadyRunningError


@pytest.fixture
def fake_service(monkeypatch):
    """Replace everything main() builds, keeping the IngestionService kwargs."""
    service = Mock()
    captured = {}

    def make_service(*args, **kwargs):
        captured.update(kwargs)
        return service

    monkeypatch.setattr(cli, "get_session_factory", lambda: Mock)
    monkeypatch.setattr(cli, "get_skritter_access_token", lambda: "token")
    monkeypatch.setattr(cli, "SkritterClient", Mock())
    monkeypatch.setattr(cli, "IngestionService", make_service)
    return service, captured


def test_refresh_flag_reaches_the_service(fake_service, monkeypatch):
    service, captured = fake_service
    monkeypatch.setattr("sys.argv", ["sync-skritter", "--all", "--refresh"])

    cli.main()

    assert captured["refresh"] is True
    service.run_all_lists.assert_called_once()


def test_sync_already_running_exits_cleanly(fake_service, monkeypatch):
    service, captured = fake_service
    service.run_all_lists.side_effect = SyncAlreadyRunningError()
    monkeypatch.setattr("sys.argv", ["sync-skritter", "--all"])

    cli.main()  # no SystemExit: a skipped scheduled run isn't a failure

    assert captured["refresh"] is False
