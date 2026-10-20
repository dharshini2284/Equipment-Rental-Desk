import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.persistence.database import create_db_engine, create_session_factory
from app.persistence.models import Base
from app.services import items as item_service
from app.services import members as member_service

# 2026-10-20 10:00 IST. Every test that does not set its own time uses this instant.
T0 = datetime(2026, 10, 20, 4, 30, tzinfo=UTC)


# Set TEST_DATABASE_URL to a PostgreSQL URL to run the same suite against PostgreSQL
# (CI does this). The tables in that database are dropped and recreated for every test.
POSTGRES_TEST_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    if POSTGRES_TEST_URL:
        return Settings(_env_file=None, database_url=POSTGRES_TEST_URL).database_url  # type: ignore[call-arg]
    # A file (not :memory:) so several connections, e.g. from threads, see the same data.
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


def _fresh_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(database_url)
    _fresh_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def make_member(session_factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    counter = iter(range(1, 10_000))

    def _make(name: str = "Test Member", phone: str | None = None) -> int:
        phone = phone or f"+9190000{next(counter):05d}"
        with session_factory() as session:
            view = member_service.create_member(
                session,
                new_member=member_service.NewMember(name=name, phone=phone, joined_on=None),
                now=T0,
            )
        return view.member.id

    return _make


@pytest.fixture
def make_item(session_factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    def _make(name: str = "Cordless drill", replacement_value_paise: int = 450_000) -> int:
        with session_factory() as session:
            view = item_service.create_item(
                session,
                fields=item_service.ItemFields(
                    name=name,
                    category="Power tools",
                    replacement_value_paise=replacement_value_paise,
                ),
                now=T0,
            )
        return view.item.id

    return _make


@pytest.fixture
def api_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=database_url,
        allow_test_clock=True,
        cors_origins="http://localhost:5173",
        log_level="WARNING",
    )


@pytest.fixture
def client(api_settings: Settings) -> Iterator[TestClient]:
    app = create_app(api_settings)
    _fresh_schema(app.state.engine)
    # raise_server_exceptions=False lets tests see the 500 response the client would get.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.state.engine.dispose()


def clock_header(when: datetime) -> dict[str, str]:
    return {"X-Test-Clock": when.isoformat()}
