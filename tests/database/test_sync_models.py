import pytest

from story_generator.ingestion.persistence.models import (
    RawSkritterPayload,
    SyncRun,
)


@pytest.mark.db
def test_create_sync_run_and_raw_payload(db_session):
    sync_run = SyncRun(
        status="running",
    )

    db_session.add(sync_run)
    db_session.flush()  # assigns sync_run.id

    payload = RawSkritterPayload(
        sync_run_id=sync_run.id,
        request_path="/vocablists",
        request_params={},
        response_status=200,
        payload={"lists": []},
    )

    db_session.add(payload)
    db_session.commit()

    saved_sync = db_session.query(SyncRun).filter_by(id=sync_run.id).one()

    saved_payload = db_session.query(RawSkritterPayload).filter_by(id=payload.id).one()

    assert saved_sync.status == "running"
    assert saved_payload.sync_run_id == saved_sync.id
    assert saved_payload.request_path == "/vocablists"
    assert saved_payload.response_status == 200
    assert saved_payload.payload == {"lists": []}
