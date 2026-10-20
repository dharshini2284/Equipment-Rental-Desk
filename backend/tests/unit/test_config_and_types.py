from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql, sqlite

from app.config import Settings
from app.persistence.types import UTCDateTime

IST = timezone(timedelta(hours=5, minutes=30))


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class TestSettings:
    @pytest.mark.parametrize(
        "url",
        ["postgres://u:p@host/db", "postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"],
    )
    def test_postgres_urls_get_the_psycopg_driver(self, url: str) -> None:
        assert settings(database_url=url).database_url == "postgresql+psycopg://u:p@host/db"

    def test_sqlite_url_is_left_alone(self) -> None:
        assert settings(database_url="sqlite:///./x.db").database_url == "sqlite:///./x.db"

    def test_cors_origins_are_split_and_trimmed(self) -> None:
        parsed = settings(cors_origins=" https://a.example , https://b.example ,").cors_origin_list
        assert parsed == ["https://a.example", "https://b.example"]


class TestUTCDateTime:
    column_type = UTCDateTime()

    def test_naive_datetime_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Naive datetime"):
            self.column_type.process_bind_param(datetime(2026, 10, 20, 10, 0), sqlite.dialect())

    def test_ist_value_is_stored_as_utc_on_sqlite(self) -> None:
        stored = self.column_type.process_bind_param(
            datetime(2026, 10, 20, 10, 0, tzinfo=IST), sqlite.dialect()
        )
        assert stored == datetime(2026, 10, 20, 4, 30)

    def test_postgres_keeps_timezone(self) -> None:
        stored = self.column_type.process_bind_param(
            datetime(2026, 10, 20, 10, 0, tzinfo=IST), postgresql.dialect()
        )
        assert stored == datetime(2026, 10, 20, 4, 30, tzinfo=UTC)
        assert stored.tzinfo == UTC

    def test_values_read_back_are_aware_utc(self) -> None:
        naive = self.column_type.process_result_value(
            datetime(2026, 10, 20, 4, 30), sqlite.dialect()
        )
        aware = self.column_type.process_result_value(
            datetime(2026, 10, 20, 10, 0, tzinfo=IST), postgresql.dialect()
        )
        assert naive == aware == datetime(2026, 10, 20, 4, 30, tzinfo=UTC)

    def test_none_passes_through(self) -> None:
        assert self.column_type.process_bind_param(None, sqlite.dialect()) is None
        assert self.column_type.process_result_value(None, sqlite.dialect()) is None
