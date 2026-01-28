"""Database setup and connection management."""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from ..config import get_config

Base = declarative_base()

# Global engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_engine(
            config.DATABASE_URL,
            pool_pre_ping=True,  # Check connection health
            pool_recycle=300,  # Recycle connections every 5 minutes
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )
    return _SessionLocal


def get_db() -> Session:
    """Get a database session.

    For use in Flask request context where session lifecycle
    is managed by the request.
    """
    SessionLocal = get_session_factory()
    return SessionLocal()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Usage:
        with get_db_session() as db:
            db.query(...)
    """
    session = get_db()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize database tables."""
    # Import all models to register them with Base
    from . import gmail_account, whitelist, processed_email  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    """Drop and recreate all tables (for testing only)."""
    from . import gmail_account, whitelist, processed_email  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def close_db() -> None:
    """Close database connections."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
    _SessionLocal = None
