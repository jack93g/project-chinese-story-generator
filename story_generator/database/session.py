import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@lru_cache
def _session_factory(database_url: str) -> sessionmaker:
    """Create one session factory per configured database URL."""
    return sessionmaker(autocommit=False, autoflush=False, bind=create_engine(database_url))


def get_session_factory() -> sessionmaker:
    """Return a database session factory, requiring configuration only on use."""
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Configure it before using a database-backed endpoint."
        )
    return _session_factory(database_url)


