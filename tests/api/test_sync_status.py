import pytest

from story_generator.ingestion.persistence.models import SyncRun

pytestmark = pytest.mark.db


def test_sync_status_returns_empty_state_when_no_runs(client):
    response = client.get("/sync-status")

    assert response.status_code == 200
    assert response.json() == {"latest_run": None}


def test_sync_status_returns_succeeded_run(client, db_session):
    sync_run = SyncRun(
        source="skritter",
        status="succeeded",
        summary={"vocabulary_items_upserted": 42, "lists_upserted": 3},
    )

    db_session.add(sync_run)
    db_session.flush()

    response = client.get("/sync-status")

    assert response.status_code == 200

    data = response.json()["latest_run"]

    assert data["id"] == sync_run.id
    assert data["source"] == "skritter"
    assert data["status"] == "succeeded"
    assert data["started_at"] is not None
    assert data["completed_at"] is None
    assert data["error_message"] is None
    assert data["summary"] == {"vocabulary_items_upserted": 42, "lists_upserted": 3}


def test_sync_status_returns_failed_run_with_error_message(client, db_session):
    sync_run = SyncRun(
        source="skritter",
        status="failed",
        error_message="Skritter API returned 503",
    )

    db_session.add(sync_run)
    db_session.flush()

    response = client.get("/sync-status")

    assert response.status_code == 200

    data = response.json()["latest_run"]

    assert data["id"] == sync_run.id
    assert data["status"] == "failed"
    assert data["error_message"] == "Skritter API returned 503"
    assert data["summary"] == {}


def test_sync_status_returns_most_recent_run(client, db_session):
    older_run = SyncRun(source="skritter", status="succeeded")
    newer_run = SyncRun(source="skritter", status="running")

    db_session.add_all([older_run, newer_run])
    db_session.flush()

    response = client.get("/sync-status")

    assert response.status_code == 200

    data = response.json()["latest_run"]

    assert data["id"] == newer_run.id
    assert data["status"] == "running"


def test_sync_status_does_not_expose_raw_payloads(client, db_session):
    sync_run = SyncRun(source="skritter", status="succeeded")

    db_session.add(sync_run)
    db_session.flush()

    response = client.get("/sync-status")

    assert response.status_code == 200
    assert "payloads" not in response.json()["latest_run"]
