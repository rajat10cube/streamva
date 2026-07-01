"""Database engine, session, and SQLite pragmas."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.db_url(),
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Phase-0 bootstrap: create tables directly.

    Superseded by Alembic migrations once the first revision is generated
    (``alembic revision --autogenerate``). Safe to keep as a dev fallback.
    """
    from . import models  # noqa: F401  -- register models on Base.metadata
    from .search import FTS_DDL

    # Migration: the legacy single-user `progress` table (no user_id) is dropped
    # and recreated per-user. (Pre-1.0; old progress is not carried over.)
    with engine.begin() as conn:
        info = conn.exec_driver_sql("PRAGMA table_info(progress)").fetchall()
        if info and not any(row[1] == "user_id" for row in info):
            conn.exec_driver_sql("DROP TABLE progress")

    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # add user.all_libraries to pre-existing DBs
        uinfo = conn.exec_driver_sql('PRAGMA table_info("user")').fetchall()
        if uinfo and not any(row[1] == "all_libraries" for row in uinfo):
            conn.exec_driver_sql(
                'ALTER TABLE "user" ADD COLUMN all_libraries BOOLEAN NOT NULL DEFAULT 1'
            )
        # add course.provider to pre-existing DBs
        cinfo = conn.exec_driver_sql("PRAGMA table_info(course)").fetchall()
        if cinfo and not any(row[1] == "provider" for row in cinfo):
            conn.exec_driver_sql("ALTER TABLE course ADD COLUMN provider VARCHAR")
        conn.exec_driver_sql(FTS_DDL)

    from .auth import ensure_admin  # seed the first admin from configured creds

    ensure_admin()
