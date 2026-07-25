import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load variables from a .env file into the environment (if present)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Add it to your .env file, e.g. "
        "DATABASE_URL=postgresql://user:password@localhost:5432/dbname"
    )

# The engine manages the pool of connections to PostgreSQL
engine = create_engine(DATABASE_URL)

# SessionLocal is a factory for short-lived database sessions.
# Each request should create its own session, use it, then close it.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



