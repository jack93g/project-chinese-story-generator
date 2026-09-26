from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, update
from sqlalchemy.orm import Session, joinedload

from story_generator.auth.persistence.models import AuthEvent, AuthSession, User


class AuthRepository:
    """Persistence operations for users, login sessions and auth events.

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

    def revoke_session(self, token_hash: str, now: datetime) -> tuple[int, int] | None:
        """Revoke a live session. Returns its (session id, user id), or None
        if no unrevoked session has that token."""
        row = self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(AuthSession.id, AuthSession.user_id)
        ).one_or_none()
        return None if row is None else (row.id, row.user_id)

    def revoke_all_sessions(self, user_id: int, now: datetime) -> None:
        self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    def add_event(self, event: AuthEvent) -> None:
        self.session.add(event)
        self.session.flush()

    def recent_events(
        self, limit: int, event_types: Sequence[str] | None = None
    ) -> list[AuthEvent]:
        query = self.session.query(AuthEvent).options(joinedload(AuthEvent.user))
        if event_types is not None:
            query = query.filter(AuthEvent.event_type.in_(event_types))
        return (
            query.order_by(AuthEvent.occurred_at.desc(), AuthEvent.id.desc())
            .limit(limit)
            .all()
        )

    def delete_events_before(self, cutoff: datetime) -> int:
        result = self.session.execute(
            delete(AuthEvent).where(AuthEvent.occurred_at < cutoff)
        )
        return result.rowcount
