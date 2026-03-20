"""
SQLAlchemy engine, session factory, and declarative base.
Shared across all ORM models (User, Subscription, etc.).
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a SQLAlchemy session, closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all ORM-managed tables if they don't exist, and run column migrations."""
    Base.metadata.create_all(bind=engine)
    # Column migrations — wrapped in try/except so startup is never blocked
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE user_usage ADD COLUMN IF NOT EXISTS occasion_count INTEGER NOT NULL DEFAULT 0"
            ))
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            conn.commit()
    except Exception as e:
        import logging
        logging.warning(f"[DB migration] Non-fatal error: {e}")
