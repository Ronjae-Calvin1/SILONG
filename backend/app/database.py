"""
Database setup.

Dev: SQLite (zero config, file-based).
Prod: swap DATABASE_URL to a Postgres URL — SQLAlchemy code below doesn't change.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Importing config first loads backend/.env, so DATABASE_URL can be set there.
from . import config  # noqa: F401,E402

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./typhoon.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
