
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func

from story_generator.database.models import (
    VocabularyList,
    VocabularyItem as VocabularyItemModel,
    list_vocabulary,
    SyncRun,
    RawSkritterPayload,
)

from story_generator.vocabulary.models import VocabularyItem

# NOTE: this class wraps a single Session and is instantiated once per transactional
# "flavour" — vocab/list writes commit once at the end of an import (caller-controlled),
# while sync-tracking writes (create_sync_run, add_raw_payload, complete/fail_sync_run)
# commit immediately so they survive even if the import transaction later rolls back.

class Repository:
    def __init__(self, session: Session):
        self.session = session

    def ensure_list(self, skritter_list_id: str, name: str) -> int:
        stmt = (
            pg_insert(VocabularyList)
            .values(skritter_list_id=skritter_list_id, name=name)
            .on_conflict_do_nothing(index_elements=["skritter_list_id"])
        )
        self.session.execute(stmt)

        result = self.session.query(VocabularyList.id).filter_by(
            skritter_list_id=skritter_list_id
        ).one()

        return result.id

    def ensure_vocab(self, vocab: VocabularyItem) -> tuple[int, bool]:
        stmt = (
            pg_insert(VocabularyItemModel)
            .values(
                skritter_vocab_id=vocab.skritter_vocab_id,
                language=vocab.language,
                writing=vocab.writing,
                reading=vocab.reading,
                definition_en=vocab.definition_en,
            )
            .on_conflict_do_nothing(index_elements=["skritter_vocab_id"])
        )
        result = self.session.execute(stmt)
        inserted = result.rowcount > 0

        row = self.session.query(VocabularyItemModel.id).filter_by(
            skritter_vocab_id=vocab.skritter_vocab_id
        ).one()

        return row.id, inserted

    def link_vocab_to_list(self, list_id: int, vocabulary_id: int) -> None:
        stmt = (
            pg_insert(list_vocabulary)
            .values(list_id=list_id, vocabulary_id=vocabulary_id)
            .on_conflict_do_nothing(index_elements=["list_id", "vocabulary_id"])
        )
        self.session.execute(stmt)

    # --- Sync run / raw payload tracking -----------------------------
    # NOTE: these methods commit immediately and are intended to be called
    # on a *separate* session from the one used for vocab/list writes, so
    # that sync tracking survives even if the import transaction rolls back.

    def create_sync_run(self, source: str = "skritter") -> SyncRun:
        sync_run = SyncRun(source=source, status="running")
        self.session.add(sync_run)
        self.session.commit()
        return sync_run

    def add_raw_payload(
        self,
        sync_run_id: int,
        request_path: str,
        request_params: dict,
        response_status: int,
        payload,
    ) -> RawSkritterPayload:
        raw_payload = RawSkritterPayload(
            sync_run_id=sync_run_id,
            request_path=request_path,
            request_params=request_params or {},
            response_status=response_status,
            payload=payload,
        )
        self.session.add(raw_payload)
        self.session.commit()
        return raw_payload

    def complete_sync_run(self, sync_run_id: int, summary: dict) -> None:
        sync_run = self.session.query(SyncRun).filter_by(id=sync_run_id).one()
        sync_run.status = "succeeded"
        sync_run.completed_at = func.now()
        sync_run.summary = summary
        self.session.commit()

    def fail_sync_run(self, sync_run_id: int, error_message: str, summary: dict | None = None) -> None:
        sync_run = self.session.query(SyncRun).filter_by(id=sync_run_id).one()
        sync_run.status = "failed"
        sync_run.completed_at = func.now()
        sync_run.error_message = error_message
        if summary is not None:
            sync_run.summary = summary
        self.session.commit()
