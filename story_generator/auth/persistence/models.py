from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Text, func
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
