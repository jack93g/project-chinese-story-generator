from collections.abc import Generator

from sqlalchemy.orm import Session

from story_generator.database.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for a single request."""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()