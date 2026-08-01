import os

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from fastapi.testclient import TestClient

from story_generator.api.app import create_app
from story_generator.api.dependencies import get_db

load_dotenv()


def _get_test_database_url() -> str:
    """
    Validate and return TEST_DATABASE_URL. Called lazily, only when a test
    actually requests database access, so `pytest -m "not db"` runs fine
    even without PostgreSQL configured.
    """
    test_url = os.getenv("TEST_DATABASE_URL")
    dev_url = os.getenv("DATABASE_URL")

    if test_url is None:
        raise RuntimeError("TEST_DATABASE_URL is not set. Add it to your .env file.")

    if test_url == dev_url:
        raise RuntimeError(
            "TEST_DATABASE_URL is the same as DATABASE_URL — refusing to run tests "
            "against your real database. Set TEST_DATABASE_URL to a separate database."
        )

    if "test" not in test_url:
        raise RuntimeError(
            f"TEST_DATABASE_URL does not look like a test database: {test_url}. "
            "Refusing to run tests against a database without 'test' in its name."
        )

    # Direct database access during integration tests uses this URL.
    os.environ["DATABASE_URL"] = test_url

    return test_url


@pytest.fixture(scope="session")
def test_database_url():
    return _get_test_database_url()


@pytest.fixture(scope="session")
def apply_migrations(test_database_url):
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_database_url)

    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


@pytest.fixture(scope="session")
def engine(test_database_url, apply_migrations):
    return create_engine(test_database_url)


@pytest.fixture
def db_session(engine):
    """
    Provide a database session wrapped in a transaction that's rolled back
    after each test, so tests never leak data into one another.
    """
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    nested = connection.begin_nested()

    def restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not trans._parent.nested:
            nested = connection.begin_nested()

    event.listen(session, "after_transaction_end", restart_savepoint)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def two_sessions(engine):
    """
    Two independent sessions on two independent connections/transactions —
    unlike `db_session`, these are NOT wrapped in a shared rolled-back
    transaction, because the sync-tracking tests specifically need to prove
    that a commit on one session survives a rollback on the other.

    Cleans up afterward by closing both sessions (releasing any locks/open
    transactions) BEFORE truncating the tables they touched — order matters
    here, since truncating while a session still holds an open transaction
    on those tables will block indefinitely.
    """
    session_a = sessionmaker(bind=engine)()
    session_b = sessionmaker(bind=engine)()
    yield session_a, session_b
    session_a.close()
    session_b.close()
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE TABLE raw_skritter_payloads, sync_runs, "
            "list_vocabulary, vocabulary_items, vocabulary_lists RESTART IDENTITY CASCADE"
        ))

@pytest.fixture
def client(db_session):
    """
    FastAPI test client backed by the transactional test database.
    """
    app = create_app()

    app.dependency_overrides[get_db] = lambda: db_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
