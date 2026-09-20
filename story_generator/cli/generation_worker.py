"""
Run the durable story-generation worker.

    python -m story_generator.cli.generation_worker
    python -m story_generator.cli.generation_worker --once
    python -m story_generator.cli.generation_worker --poll-interval 2 --stale-after-minutes 10
"""

import argparse
from datetime import timedelta

from story_generator.database.session import get_session_factory
from story_generator.generation.persistence.repository import (
    GenerationRequestRepository,
)
from story_generator.generation.persistence.service import GenerationRequestService
from story_generator.generation.providers.openai import build_openai_provider
from story_generator.generation.providers.provider_registry import (
    assert_current_provider_approved,
)
from story_generator.generation.worker import GenerationWorker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one request and exit"
    )
    parser.add_argument("--stale-after-minutes", type=float, default=15.0)
    args = parser.parse_args()

    # Fail fast, before touching the DB or building anything else: if the
    # configured (OPENAI_PROVIDER_LABEL, OPENAI_MODEL, OPENAI_BASE_URL)
    # combination has no recorded, reviewed comparison, this process should
    # not start at all rather than start and fail on the first claimed
    # request. build_openai_provider() below also enforces this internally,
    # but that's an implementation detail of that factory — asserting it
    # explicitly here makes the "must be approved before this process does
    # anything" requirement independent of that and visible at the call
    # site, per M3-7.
    assert_current_provider_approved()

    session_factory = get_session_factory()
    provider = build_openai_provider()
    worker = GenerationWorker(provider=provider)
    stale_after = timedelta(minutes=args.stale_after_minutes)

    if args.once:
        db = session_factory()
        try:
            repository = GenerationRequestRepository(db)
            service = GenerationRequestService(repository)
            result = service.reclaim_stale(stale_after)
            if result["failed"] or result["requeued"]:
                print(
                    f"Reclaim: requeued {result['requeued']}, exhausted/failed {result['failed']}"
                )
            processed = worker.run_once(db)
            print("Processed one request." if processed else "No queued requests.")
        finally:
            db.close()
        return

    worker.run_forever(
        session_factory, poll_interval=args.poll_interval, stale_after=stale_after
    )


if __name__ == "__main__":
    main()
