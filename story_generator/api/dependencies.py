from collections.abc import Generator

from sqlalchemy.orm import Session

from story_generator.database.session import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for a single request."""
    db = get_session_factory()()

    try:
        yield db
    finally:
        db.close()
