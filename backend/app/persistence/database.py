"""Engine and session setup.

SQLite note: pysqlite starts transactions lazily, which lets two writers read the
same row before either one writes. Every transaction here starts with
BEGIN IMMEDIATE instead, so writers are serialised and a read-check-write
sequence inside one transaction cannot interleave with another. On PostgreSQL
the services take row locks (SELECT ... FOR UPDATE) for the same effect.
"""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

SQLITE_BUSY_TIMEOUT_SECONDS = 15


def create_db_engine(database_url: str) -> Engine:
    if not database_url.startswith("sqlite"):
        return create_engine(database_url, pool_pre_ping=True)

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_SECONDS},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
        # Hand transaction control to SQLAlchemy so the "begin" hook decides how to begin.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
