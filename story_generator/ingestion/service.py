import logging

from story_generator.ingestion.persistence.repository import SyncRunRepository
from story_generator.ingestion.schemas import SyncRunResponse, SyncStatusResponse
from story_generator.vocabulary.parser import parse_vocab

logger = logging.getLogger(__name__)

# Raw Skritter responses are kept for debugging recent runs only: pruning
# happens as a sync starts, so the newest RAW_PAYLOAD_RUNS_KEPT earlier runs
# keep theirs, plus the run in progress. Older runs keep their sync_runs row
# (status, summary, error) but lose their payloads.
RAW_PAYLOAD_RUNS_KEPT = 10

INTERRUPTED_RUN_MESSAGE = "Interrupted: the sync process stopped before finishing."


class SyncAlreadyRunningError(Exception):
    """Raised when another sync holds the sync lock."""

    def __init__(self):
        super().__init__("Another Skritter sync is already running.")


class SyncPartialFailureError(Exception):
    """Raised when a batch sync completes but one or more lists failed."""

    def __init__(self, failures: list):
        self.failures = failures
        summary = "; ".join(f"{f['name']} ({f['id']}): {f['error']}" for f in failures)
        super().__init__(f"{len(failures)} list(s) failed during sync: {summary}")


class IngestionService:
    def __init__(
        self,
        client,
        vocabulary_repository,
        vocabulary_session,
        sync_run_repository,
        tracking_session,
        *,
        sync_lock,
        refresh: bool = False,
    ):
        self.client = client
        self.vocabulary_repository = vocabulary_repository
        self.vocabulary_session = vocabulary_session
        self.sync_run_repository = sync_run_repository
        self.tracking_session = tracking_session
        self.sync_lock = sync_lock
        # False: only fetch words that aren't in the database yet (the words
        # already there are still linked to the list). True: re-fetch every
        # word, which picks up definition/reading edits made in Skritter.
        self.refresh = refresh

    def import_list(self, list_id: str) -> dict:
        list_data = self.client.get_list(list_id)
        imported = 0
        existing = 0
        try:
            list_db_id = self.vocabulary_repository.ensure_list(
                list_data["id"],
                list_data["name"],
            )
            # A word can appear in more than one section of a list.
            vocab_ids = list(dict.fromkeys(list_data["vocab_ids"]))
            known = (
                {}
                if self.refresh
                else self.vocabulary_repository.get_ids_by_skritter_vocab_ids(vocab_ids)
            )
            to_fetch = [vocab_id for vocab_id in vocab_ids if vocab_id not in known]
            logger.info(
                "Importing list '%s' (%d vocabulary items, %d to fetch)",
                list_data["name"],
                len(vocab_ids),
                len(to_fetch),
            )
            in_list = set(known.values())
            for vocab_db_id in in_list:
                self.vocabulary_repository.link_vocab_to_list(list_db_id, vocab_db_id)
            existing += len(known)

            total = len(to_fetch)
            for i, vocab_id in enumerate(to_fetch, start=1):
                if i % 25 == 0 or i == total:
                    logger.info("Fetch progress: %d/%d", i, total)
                vocab_response = self.client.get_vocab(vocab_id)
                vocab = parse_vocab(vocab_response)
                vocab_db_id, inserted = self.vocabulary_repository.ensure_vocab(vocab)
                self.vocabulary_repository.link_vocab_to_list(
                    list_db_id,
                    vocab_db_id,
                )
                in_list.add(vocab_db_id)
                if inserted:
                    imported += 1
                else:
                    existing += 1
            unlinked = self._unlink_removed_vocab(list_db_id, list_data, in_list)
            self.vocabulary_session.commit()
        except Exception:
            self.vocabulary_session.rollback()
            raise
        logger.info("Finished '%s'", list_data["name"])
        return {
            "lists_processed": 1,
            "vocab_processed": imported + existing,
            "vocab_imported": imported,
            "vocab_skipped": existing,
            "vocab_fetched": len(to_fetch),
            "vocab_unlinked": unlinked,
            "failures": [],
        }

    def _unlink_removed_vocab(
        self, list_db_id: int, list_data: dict, in_list: set[int]
    ) -> int:
        """Drop the list's links to words no longer in it in Skritter."""
        if not in_list:
            # More likely a bad response than a list emptied on purpose, so
            # keep what's there rather than wiping the list.
            stored = self.vocabulary_repository.count_list_items(list_db_id)
            if stored:
                logger.warning(
                    "Skritter returned no words for list '%s', which has %d; "
                    "keeping them",
                    list_data["name"],
                    stored,
                )
            return 0
        unlinked = self.vocabulary_repository.unlink_vocab_not_in(list_db_id, in_list)
        if unlinked:
            logger.info(
                "Removed %d word(s) no longer in '%s'", unlinked, list_data["name"]
            )
        return unlinked

    def import_all_lists(self) -> dict:
        lists = self.client.get_lists()
        logger.info("Found %d lists to import", len(lists))

        lists_processed = 0
        vocab_imported = 0
        vocab_skipped = 0
        vocab_fetched = 0
        vocab_unlinked = 0
        failures = []

        for i, vocab_list in enumerate(lists, start=1):
            logger.info("Importing list %d/%d: '%s'", i, len(lists), vocab_list["name"])
            try:
                result = self.import_list(vocab_list["id"])
                lists_processed += 1
                vocab_imported += result["vocab_imported"]
                vocab_skipped += result["vocab_skipped"]
                vocab_fetched += result["vocab_fetched"]
                vocab_unlinked += result["vocab_unlinked"]
            except Exception as exc:
                logger.exception(
                    "Failed to import list '%s' (%s)",
                    vocab_list["name"],
                    vocab_list["id"],
                )
                failures.append(
                    {
                        "id": vocab_list["id"],
                        "name": vocab_list["name"],
                        "error": str(exc),
                    }
                )

        logger.info(
            "Finished: %d/%d lists imported successfully", lists_processed, len(lists)
        )
        if failures:
            logger.error("%d list(s) failed during import", len(failures))

        lists_archived = self._archive_removed_lists(lists)

        return {
            "lists_processed": lists_processed,
            "vocab_processed": vocab_imported + vocab_skipped,
            "vocab_imported": vocab_imported,
            "vocab_skipped": vocab_skipped,
            "vocab_fetched": vocab_fetched,
            "vocab_unlinked": vocab_unlinked,
            "lists_archived": lists_archived,
            "failures": failures,
        }

    def _archive_removed_lists(self, lists: list[dict]) -> int:
        """Archive stored lists that Skritter no longer returns.

        Only a full sync can do this: it's the only time we see every list.
        """
        if not lists:
            # As with an empty list: keep everything rather than trust it.
            if self.vocabulary_repository.count_lists():
                logger.warning("Skritter returned no lists; archiving none")
            return 0
        try:
            archived = self.vocabulary_repository.archive_lists_not_in(
                {vocab_list["id"] for vocab_list in lists}
            )
            self.vocabulary_session.commit()
        except Exception:
            self.vocabulary_session.rollback()
            raise
        for name in archived:
            logger.info("Archived list '%s': no longer in Skritter", name)
        return len(archived)

    # --- Sync run tracking (separate session, commits independently) ----

    def run_all_lists(self) -> dict:
        """Public entry point: sync every list, tracked as one SyncRun."""
        return self._with_sync_tracking(self.import_all_lists)

    def run_single_list(self, list_id: str) -> dict:
        """Public entry point: sync one list, tracked as one SyncRun."""
        return self._with_sync_tracking(lambda: self.import_list(list_id))

    def _with_sync_tracking(self, fn) -> dict:
        if not self.sync_lock.try_acquire():
            raise SyncAlreadyRunningError()
        try:
            return self._run_tracked(fn)
        finally:
            self.sync_lock.release()

    def _run_tracked(self, fn) -> dict:
        # Holding the lock proves no other sync is running, so any run still
        # marked "running" belongs to a process that died mid-sync.
        interrupted = self.sync_run_repository.fail_interrupted_runs(
            INTERRUPTED_RUN_MESSAGE
        )
        if interrupted:
            logger.warning("Marked %d interrupted sync run(s) as failed", interrupted)
        self.sync_run_repository.prune_raw_payloads(keep_runs=RAW_PAYLOAD_RUNS_KEPT)
        sync_run = self.sync_run_repository.create_sync_run()
        self.tracking_session.commit()
        self.client.on_response = self._make_payload_recorder(sync_run.id)
        result = None
        try:
            result = fn()
            if result.get("failures"):
                raise SyncPartialFailureError(result["failures"])
        except Exception as exc:
            self.sync_run_repository.fail_sync_run(
                sync_run.id,
                self._safe_error_message(exc),
                summary=result,  # None for a hard crash, populated for partial failure
            )
            self.tracking_session.commit()
            raise
        else:
            self.sync_run_repository.complete_sync_run(sync_run.id, result)
            self.tracking_session.commit()
            return result
        finally:
            self.client.on_response = None

    def _make_payload_recorder(self, sync_run_id: int):
        def record(request_path, request_params, response_status, payload):
            self.sync_run_repository.add_raw_payload(
                sync_run_id, request_path, request_params, response_status, payload
            )
            self.tracking_session.commit()

        return record

    def _safe_error_message(self, exc: Exception) -> str:
        # Deliberately class name + message only — never a full traceback or
        # raw exception repr, since httpx/library exceptions can embed request
        # details. Truncated defensively for storage.
        message = f"{type(exc).__name__}: {exc}"
        return message[:2000]


class SyncStatusService:
    def __init__(self, repository: SyncRunRepository):
        self.repository = repository

    def get_latest(self) -> SyncStatusResponse:
        sync_run = self.repository.get_latest()

        if sync_run is None:
            return SyncStatusResponse(latest_run=None)

        return SyncStatusResponse(
            latest_run=SyncRunResponse(
                id=sync_run.id,
                source=sync_run.source,
                status=sync_run.status,
                started_at=sync_run.started_at,
                completed_at=sync_run.completed_at,
                error_message=sync_run.error_message,
                summary=sync_run.summary,
            )
        )
