from datetime import UTC, datetime, timedelta

import pytest

from app.domain.errors import InvalidTransitionError
from app.domain.timing import (
    days_overdue,
    desk_date,
    due_at_for,
    ensure_not_before,
    is_overdue,
    is_reservation_expired,
    reservation_expires_at,
)

RESERVED_AT = datetime(2026, 10, 20, 4, 30, tzinfo=UTC)
DUE_AT = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


class TestReservationExpiry:
    def test_hold_lasts_48_hours(self) -> None:
        assert reservation_expires_at(RESERVED_AT) == RESERVED_AT + timedelta(hours=48)

    def test_still_held_at_47h59m(self) -> None:
        assert not is_reservation_expired(
            RESERVED_AT, RESERVED_AT + timedelta(hours=47, minutes=59)
        )

    def test_still_held_one_second_before_48h(self) -> None:
        assert not is_reservation_expired(
            RESERVED_AT, RESERVED_AT + timedelta(hours=48, seconds=-1)
        )

    def test_expired_at_exactly_48h(self) -> None:
        assert is_reservation_expired(RESERVED_AT, RESERVED_AT + timedelta(hours=48))

    def test_expired_at_48h01m(self) -> None:
        assert is_reservation_expired(RESERVED_AT, RESERVED_AT + timedelta(hours=48, minutes=1))


class TestDueDateAndOverdue:
    def test_loan_period_is_seven_days(self) -> None:
        assert due_at_for(RESERVED_AT) == RESERVED_AT + timedelta(days=7)

    def test_not_overdue_at_exact_due_time(self) -> None:
        assert not is_overdue(DUE_AT, DUE_AT)
        assert days_overdue(DUE_AT, DUE_AT) == 0

    def test_not_overdue_before_due(self) -> None:
        assert days_overdue(DUE_AT, DUE_AT - timedelta(days=3)) == 0

    def test_one_second_late_counts_as_one_day(self) -> None:
        assert is_overdue(DUE_AT, DUE_AT + timedelta(seconds=1))
        assert days_overdue(DUE_AT, DUE_AT + timedelta(seconds=1)) == 1

    def test_exactly_one_day_late_is_one_day(self) -> None:
        assert days_overdue(DUE_AT, DUE_AT + timedelta(days=1)) == 1

    def test_part_day_rounds_up(self) -> None:
        assert days_overdue(DUE_AT, DUE_AT + timedelta(days=1, seconds=1)) == 2

    @pytest.mark.parametrize(
        ("late_by", "expected_days"),
        [
            (timedelta(days=14), 14),
            (timedelta(days=14, seconds=1), 15),
            (timedelta(days=20, hours=3), 21),
        ],
    )
    def test_days_overdue_boundaries(self, late_by: timedelta, expected_days: int) -> None:
        assert days_overdue(DUE_AT, DUE_AT + late_by) == expected_days


class TestDeskDate:
    def test_utc_evening_is_next_day_in_ist(self) -> None:
        # 20:00 UTC on the 20th is 01:30 IST on the 21st.
        assert desk_date(datetime(2026, 10, 20, 20, 0, tzinfo=UTC)).isoformat() == "2026-10-21"


class TestClockOrdering:
    def test_allows_same_instant(self) -> None:
        ensure_not_before(RESERVED_AT, RESERVED_AT, "reserved")

    def test_rejects_time_before_previous_event(self) -> None:
        with pytest.raises(InvalidTransitionError) as error:
            ensure_not_before(RESERVED_AT - timedelta(minutes=1), RESERVED_AT, "reserved")
        assert error.value.code == "CLOCK_BEFORE_PREVIOUS_EVENT"
