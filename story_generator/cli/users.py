import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from story_generator.auth.persistence.repository import AuthRepository
from story_generator.auth.service import (
    AuthService,
    InvalidUsernameError,
    PasswordTooShortError,
    UsernameTakenError,
    UserNotFoundError,
    normalize_username,
)
from story_generator.database.session import get_session_factory


class PasswordMismatchError(Exception):
    def __init__(self):
        super().__init__("Passwords did not match")


def prompt_new_password() -> str:
    password = getpass.getpass("New password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise PasswordMismatchError()
    return password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage login accounts. Passwords are prompted for, never "
        "passed as arguments, so they don't end up in shell history."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create a login account.")
    create.add_argument("username")

    set_password = commands.add_parser(
        "set-password",
        help="Change an account's password and log out all of its sessions.",
    )
    set_password.add_argument("username")

    return parser


def run(
    argv: Sequence[str],
    session: Session,
    read_password: Callable[[], str] = prompt_new_password,
) -> str:
    """Execute one command and commit. Returns a message for the user."""
    args = build_parser().parse_args(argv)
    service = AuthService(AuthRepository(session))
    password = read_password()

    if args.command == "create":
        user = service.create_user(args.username, password)
        message = f"Created user {user.username!r}."
    else:
        service.set_password(args.username, password)
        username = normalize_username(args.username)
        message = f"Password changed; all sessions for {username!r} logged out."

    session.commit()
    return message


def main() -> None:
    session = get_session_factory()()
    try:
        print(run(sys.argv[1:], session))
    except (
        InvalidUsernameError,
        PasswordMismatchError,
        PasswordTooShortError,
        UsernameTakenError,
        UserNotFoundError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
