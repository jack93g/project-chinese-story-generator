import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from story_generator.database.session import get_session_factory
from story_generator.vocabulary.persistence.repository import VocabularyRepository
from story_generator.vocabulary.service import (
    SkritterListNotFoundError,
    VocabularyListService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hide vocabulary lists from the app, or show them again. "
        "Lists are named by their Skritter list ID, as `list` prints it."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="Show every list and whether it's hidden.")
    hide = commands.add_parser(
        "hide",
        help="Hide lists: they keep syncing but can't be picked for stories.",
    )
    hide.add_argument("skritter_list_ids", nargs="+", metavar="SKRITTER_LIST_ID")
    show = commands.add_parser("show", help="Make hidden lists available again.")
    show.add_argument("skritter_list_ids", nargs="+", metavar="SKRITTER_LIST_ID")

    return parser


def _status(vocab_list) -> str:
    if vocab_list.archived_at is not None:
        return "archived"
    return "hidden" if vocab_list.hidden else ""


def run(argv: Sequence[str], session: Session) -> str:
    """Execute one command and commit. Returns a message for the user."""
    args = build_parser().parse_args(argv)
    service = VocabularyListService(VocabularyRepository(session))

    if args.command == "list":
        rows = [
            f"{vocab_list.skritter_list_id:<18} {count:>5}  {_status(vocab_list):<8}  "
            f"{vocab_list.name}"
            for vocab_list, count in service.list_all()
        ]
        header = f"{'SKRITTER ID':<18} {'WORDS':>5}  {'STATUS':<8}  NAME"
        return "\n".join([header, *rows])

    hidden = args.command == "hide"
    lists = service.set_hidden(args.skritter_list_ids, hidden)
    session.commit()
    names = ", ".join(repr(vocab_list.name) for vocab_list in lists)
    return f"{'Hidden' if hidden else 'Visible again'}: {names}."


def main() -> None:
    session = get_session_factory()()
    try:
        print(run(sys.argv[1:], session))
    except SkritterListNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
