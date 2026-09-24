"""
Run the durable story-generation worker.

    python -m story_generator.cli.generation_worker
    python -m story_generator.cli.generation_worker --once
    python -m story_generator.cli.generation_worker --poll-interval 2 --stale-after-minutes 10

SIGTERM (what `docker compose stop` sends) and Ctrl-C stop the worker
between requests: a request already in flight finishes first.
"""

import argparse
import signal
from datetime import timedelta

from story_generator.database.session import get_session_factory
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
    parser.add_argument(
        "--reclaim-interval-minutes",
        type=float,
        default=5.0,
        help="How often to requeue stale 'running' requests (also done at startup)",
    )
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
            worker.reclaim_stale(db, stale_after)
            processed = worker.run_once(db)
            print("Processed one request." if processed else "No queued requests.")
        finally:
            db.close()
        return

    def _stop(signum, _frame):
        print(
            f"Received {signal.Signals(signum).name}; stopping after the current request."
        )
        worker.request_stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    worker.run_forever(
        session_factory,
        poll_interval=args.poll_interval,
        stale_after=stale_after,
        reclaim_interval=args.reclaim_interval_minutes * 60,
    )
    print("Worker stopped.")


if __name__ == "__main__":
    main()
