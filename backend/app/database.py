"""SQLite setup (SQLAlchemy 2.0). One engine, one session factory.

The DB file lives next to the backend code (``shiftpilot.db``) and is
created on first run. It is git-ignored — a fresh install re-seeds
from ``seed.py``, so cloning the repo never ships a stale database.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
