from story_generator.vocabulary.parser import parse_vocab

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
    ):
        self.client = client
        self.vocabulary_repository = vocabulary_repository
        self.vocabulary_session = vocabulary_session
        self.sync_run_repository = sync_run_repository
        self.tracking_session = tracking_session


    def import_list(self, list_id: str) -> dict:
        list_data = self.client.get_list(list_id)
        imported = 0
        skipped = 0
        try:
            list_db_id = self.vocabulary_repository.ensure_list(
                list_data["id"],
                list_data["name"],
            )
            total = len(list_data["vocab_ids"])
            print(f"Importing list '{list_data['name']}' ({total} vocabulary items)...")
            for i, vocab_id in enumerate(list_data["vocab_ids"], start=1):
                if i % 25 == 0 or i == total:
                    print(f"  Progress: {i}/{total}")
                vocab_response = self.client.get_vocabs(vocab_id)
                vocab = parse_vocab(vocab_response)
                vocab_db_id, inserted = self.vocabulary_repository.ensure_vocab(vocab)
                self.vocabulary_repository.link_vocab_to_list(
                    list_db_id,
                    vocab_db_id,
                )
                if inserted:
                    imported += 1
                else:
                    skipped += 1
            self.vocabulary_session.commit()
        except Exception:
            self.vocabulary_session.rollback()
            raise
        print(f"Finished '{list_data['name']}'.")
        return {
            "lists_processed": 1,
            "vocab_processed": imported + skipped,
            "vocab_imported": imported,
            "vocab_skipped": skipped,
            "failures": [],
        }

    def import_all_lists(self) -> dict:
        lists = self.client.get_lists()
        print(f"Found {len(lists)} lists to import.\n")

        lists_processed = 0
        vocab_imported = 0
        vocab_skipped = 0
        failures = []

        for i, vocab_list in enumerate(lists, start=1):
            print(f"[{i}/{len(lists)}] Importing '{vocab_list['name']}'...")
            try:
                result = self.import_list(vocab_list["id"])
                lists_processed += 1
                vocab_imported += result["vocab_imported"]
                vocab_skipped += result["vocab_skipped"]
            except Exception as exc:
                print(f"  FAILED: '{vocab_list['name']}' ({vocab_list['id']}): {exc}")
                failures.append({"id": vocab_list["id"], "name": vocab_list["name"], "error": str(exc)})

        print(f"\nFinished. {lists_processed}/{len(lists)} lists imported successfully.")
        if failures:
            print(f"{len(failures)} list(s) failed:")
            for f in failures:
                print(f"  - {f['name']} ({f['id']}): {f['error']}")

        return {
            "lists_processed": lists_processed,
            "vocab_processed": vocab_imported + vocab_skipped,
            "vocab_imported": vocab_imported,
            "vocab_skipped": vocab_skipped,
            "failures": failures,
        }

    # --- Sync run tracking (separate session, commits independently) ----

    def run_all_lists(self) -> dict:
        """Public entry point: sync every list, tracked as one SyncRun."""
        return self._with_sync_tracking(self.import_all_lists)

    def run_single_list(self, list_id: str) -> dict:
        """Public entry point: sync one list, tracked as one SyncRun."""
        return self._with_sync_tracking(lambda: self.import_list(list_id))

    def _with_sync_tracking(self, fn) -> dict:
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
