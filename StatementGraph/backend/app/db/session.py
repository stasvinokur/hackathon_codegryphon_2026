from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args: dict[str, object] = {}
if settings.postgres_dsn.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a scoped database session for request lifecycle."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
