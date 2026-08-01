import argparse
import logging
import sys

from story_generator.config import get_skritter_access_token
from story_generator.database.session import get_session_factory
from story_generator.ingestion.persistence.repository import SyncRunRepository
from story_generator.ingestion.service import IngestionService, SyncPartialFailureError
from story_generator.ingestion.skritter_client import SkritterClient
from story_generator.vocabulary.persistence.repository import VocabularyRepository

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Import vocabulary from Skritter into the database."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-id", help="Import a single Skritter list by ID.")
    group.add_argument("--all", action="store_true", help="Import all Skritter lists.")
    args = parser.parse_args()

    session_factory = get_session_factory()
    vocabulary_session = session_factory()
    tracking_session = session_factory()
    try:
        service = IngestionService(
            SkritterClient(get_skritter_access_token()),
            VocabularyRepository(vocabulary_session),
            vocabulary_session,
            SyncRunRepository(tracking_session),
            tracking_session,
        )
        if args.list_id:
            service.run_single_list(args.list_id)
        else:
            service.run_all_lists()
    except SyncPartialFailureError as exc:
        logger.error("Sync completed with failures: %s", exc)
        sys.exit(1)
    finally:
        vocabulary_session.close()
        tracking_session.close()


if __name__ == "__main__":
    main()
