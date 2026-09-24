from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from story_generator.auth.persistence.models import AuthSession, User


class AuthRepository:
    """Persistence operations for users and login sessions.

    Transaction boundaries are controlled by the caller.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_user_by_username(self, username: str) -> User | None:
        return self.session.query(User).filter(User.username == username).one_or_none()

    def add_user(self, user: User) -> None:
        self.session.add(user)
        self.session.flush()

    def add_session(self, auth_session: AuthSession) -> None:
        self.session.add(auth_session)
        self.session.flush()

    def get_active_session(self, token_hash: str, now: datetime) -> AuthSession | None:
        return (
            self.session.query(AuthSession)
            .filter(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .one_or_none()
        )

    def revoke_session(self, token_hash: str, now: datetime) -> None:
        self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def revoke_all_sessions(self, user_id: int, now: datetime) -> None:
        self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
