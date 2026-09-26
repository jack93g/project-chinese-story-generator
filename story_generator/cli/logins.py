import argparse
import sys
from collections.abc import Sequence
from datetime import UTC

from sqlalchemy.orm import Session

from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import (
    AUTH_EVENT_RETENTION,
    AuthEventSummary,
    AuthService,
)
from story_generator.database.session import get_session_factory

# The user agent is cut short in the table; the full one (up to 512
# characters) is in auth_events.user_agent.
_USER_AGENT_WIDTH = 60


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review login attempts and logouts (the auth_events table), "
        f"or delete those older than {AUTH_EVENT_RETENTION.days} days."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    recent = commands.add_parser("recent", help="The latest events, newest first.")
    recent.add_argument(
        "--limit", type=_positive_int, default=20, help="How many (default 20)."
    )
    recent.add_argument(
        "--failed", action="store_true", help="Only failed login attempts."
    )
    commands.add_parser(
        "purge",
        help=f"Delete events older than {AUTH_EVENT_RETENTION.days} days "
        "(run daily by cron).",
    )

    return parser


def _row(event: AuthEventSummary) -> str:
    user_agent = event.user_agent or "-"
    if len(user_agent) > _USER_AGENT_WIDTH:
        user_agent = user_agent[: _USER_AGENT_WIDTH - 1] + "…"
    return (
        f"{event.occurred_at.astimezone(UTC):%Y-%m-%d %H:%M:%S}  "
        f"{event.event_type:<20}  {event.username or '-':<12}  "
        f"{event.client_ip or '-':<39}  {event.session_id or '-':>7}  {user_agent}"
    )


def run(argv: Sequence[str], session: Session) -> str:
    """Execute one command, committing only for `purge`. Returns the text to
    print."""
    args = build_parser().parse_args(argv)
    service = AuthService(AuthRepository(session))

    if args.command == "purge":
        deleted = service.delete_expired_events()
        session.commit()
        return (
            f"Deleted {deleted} auth events older than "
            f"{AUTH_EVENT_RETENTION.days} days."
        )

    events = service.recent_events(args.limit, failed_only=args.failed)
    if not events:
        return "No failed login attempts." if args.failed else "No auth events."
    header = (
        f"{'OCCURRED (UTC)':<19}  {'EVENT':<20}  {'USER':<12}  {'CLIENT IP':<39}  "
        f"{'SESSION':>7}  USER AGENT"
    )
    return "\n".join([header, *(_row(event) for event in events)])


def main() -> None:
    session = get_session_factory()()
    try:
        print(run(sys.argv[1:], session))
    finally:
        session.close()


if __name__ == "__main__":
    main()
