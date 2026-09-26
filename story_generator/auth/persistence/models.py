from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from story_generator.database.base import Base


class User(Base):
    """
    A login account. Accounts are created from the command line
    (`manage-users create`); there is no sign-up endpoint. Every account sees
    the same data: this is a login gate, not multi-tenancy.
    """

    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    # Stored normalised (trimmed, lower-case) by AuthService.
    username = Column(Text, nullable=False, unique=True)
    # Argon2 hash in PHC string format; the salt and parameters are embedded.
    password_hash = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthSession(Base):
    """
    One browser login. The browser holds a random token in a cookie; only its
    SHA-256 hash is stored here, so reading this table (or a backup of it)
    doesn't let anyone log in.
    """

    __tablename__ = "auth_sessions"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash = Column(Text, nullable=False, unique=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")

    __table_args__ = (Index("auth_sessions_user_id_idx", "user_id"),)


class AuthEvent(Base):
    """
    One login attempt or logout, kept as an event for analysis and abuse
    investigation. Only attempts the rate limiter let through are recorded,
    so a flood of 429s can't fill the disk. Rows older than 90 days are
    deleted daily (`manage-logins purge`), because client_ip is personal data.

    The attempted username is never stored: people sometimes type their
    password into the username field. A login for a name that isn't an
    account is recorded as `login_unknown_user` with no user_id.

    user_id and session_id become null if the user (and with it their
    sessions) is deleted.
    """

    __tablename__ = "auth_events"

    id = Column(BigInteger, primary_key=True)
    occurred_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_type = Column(Text, nullable=False)
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The session a successful login created, or the one a logout ended.
    session_id = Column(
        BigInteger, ForeignKey("auth_sessions.id", ondelete="SET NULL"), nullable=True
    )
    # The caller's address: real in production, where the API trusts Caddy's
    # X-Forwarded-For (docker-compose.prod.yml sets FORWARDED_ALLOW_IPS).
    client_ip = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)

    user = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "event_type = ANY (ARRAY['login_succeeded'::text, "
            "'login_wrong_password'::text, 'login_unknown_user'::text, "
            "'logout'::text])",
            name="auth_events_event_type_check",
        ),
        CheckConstraint(
            "event_type <> 'login_unknown_user' OR user_id IS NULL",
            name="auth_events_unknown_user_has_no_user_check",
        ),
        CheckConstraint(
            "event_type IN ('login_succeeded', 'logout') OR session_id IS NULL",
            name="auth_events_session_id_check",
        ),
        Index("auth_events_occurred_at_idx", "occurred_at"),
        Index("auth_events_user_id_idx", "user_id"),
        Index("auth_events_session_id_idx", "session_id"),
    )
