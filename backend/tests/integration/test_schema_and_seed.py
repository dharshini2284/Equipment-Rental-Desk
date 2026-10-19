from datetime import timedelta
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.statuses import ItemStatus
from app.persistence.database import create_db_engine, create_session_factory
from app.persistence.models import Base
from app.seed import clear_database, database_has_data, seed
from app.services import items as item_service
from app.services import loans as loan_service
from app.services import members as member_service
from tests.conftest import T0

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_migrations_match_the_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert diff == []


def test_seed_creates_the_documented_scenarios(session_factory: sessionmaker[Session]) -> None:
    seed(session_factory, T0)

    with session_factory() as session:
        members = {
            v.member.name: v.member.id
            for v in member_service.list_members(
                session, search=None, status=None, limit=100, offset=0
            )[0]
        }

        def blocks(name: str) -> list[str]:
            info = member_service.get_member_detail(session, member_id=members[name], now=T0)
            return [b.code for b in info.eligibility.blocks]

        assert blocks("Meera Iyer") == ["FEE_BALANCE_OVER_LIMIT"]
        assert blocks("Farhan Qureshi") == []  # owes exactly ₹100
        assert blocks("Rohan Kulkarni") == ["LOAN_OVERDUE_TOO_LONG"]
        assert blocks("Ananya Bose") == ["MEMBER_SUSPENDED"]
        assert blocks("Lakshmi Pillai") == ["ACTIVE_LOAN_LIMIT_REACHED"]
        assert blocks("Vikram Joshi") == []

        farhan = member_service.get_member_detail(
            session, member_id=members["Farhan Qureshi"], now=T0
        )
        assert farhan.balance_paise == 10_000

        overdue, total = loan_service.list_overdue_loans(session, now=T0, limit=50, offset=0)
        assert total == 2
        assert [view.days_overdue for view in overdue] == [18, 3]

        _, in_maintenance = item_service.list_items(
            session,
            now=T0,
            status=ItemStatus.MAINTENANCE,
            search=None,
            category=None,
            limit=50,
            offset=0,
        )
        assert in_maintenance == 1

        # Aarav's 47-hour-old reservation lapses an hour later.
        _, reserved_now = item_service.list_items(
            session,
            now=T0,
            status=ItemStatus.RESERVED,
            search=None,
            category=None,
            limit=50,
            offset=0,
        )
        _, reserved_later = item_service.list_items(
            session,
            now=T0 + timedelta(hours=1),
            status=ItemStatus.RESERVED,
            search=None,
            category=None,
            limit=50,
            offset=0,
        )
        assert reserved_now - reserved_later == 1


def test_clear_database_empties_everything(session_factory: sessionmaker[Session]) -> None:
    seed(session_factory, T0)
    with session_factory() as session:
        clear_database(session)
    with session_factory() as session:
        assert not database_has_data(session)

    seed(session_factory, T0)
    with session_factory() as session:
        reseeded = member_service.list_members(
            session, search=None, status=None, limit=100, offset=0
        )[0]
        assert min(view.member.id for view in reseeded) == 1


def test_engine_enables_foreign_keys_on_sqlite(tmp_path: Path) -> None:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'fk.db').as_posix()}")
    with create_session_factory(engine)() as session:
        assert session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()
