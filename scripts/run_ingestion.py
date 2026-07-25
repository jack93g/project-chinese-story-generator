import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from story_generator.database.session import SessionLocal
from story_generator.database.repository import Repository
from story_generator.ingestion.service import IngestionService, SyncPartialFailureError
from story_generator.ingestion.skritter_client import SkritterClient
from story_generator.config import get_skritter_access_token


def main():
    parser = argparse.ArgumentParser(description="Import vocabulary from Skritter into the database.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-id", help="Import a single Skritter list by ID.")
    group.add_argument("--all", action="store_true", help="Import all Skritter lists.")
    args = parser.parse_args()

    access_token = get_skritter_access_token()

    # Two independent sessions/connections: `session` is the business-data
    # transaction (vocab/list writes, commit-once-at-the-end), `tracking_session`
    # is the sync-run/raw-payload transaction, which commits eagerly so it
    # survives even if `session` rolls back.
    session = SessionLocal()
    tracking_session = SessionLocal()
    try:
        client = SkritterClient(access_token)
        repository = Repository(session)
        tracking_repository = Repository(tracking_session)
        service = IngestionService(client, repository, session, tracking_repository)

        if args.list_id:
            service.run_single_list(args.list_id)
        else:
            service.run_all_lists()
    except SyncPartialFailureError as exc:
        print(f"Sync completed with failures: {exc}")
        sys.exit(1)
    finally:
        session.close()
        tracking_session.close()

if __name__ == "__main__":
    main()