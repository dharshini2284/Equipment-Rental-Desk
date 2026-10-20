"""Time-based rules: reservation expiry, due dates and days overdue.

All datetimes passed in here must be timezone-aware (UTC in practice).
"""

from datetime import date, datetime, timedelta

from app.domain.errors import InvalidTransitionError
from app.domain.policy import DESK_TIMEZONE, LOAN_PERIOD, RESERVATION_HOLD

ONE_DAY = timedelta(days=1)


def desk_date(now: datetime) -> date:
    """The calendar date at the desk (IST) for a UTC instant."""
    return now.astimezone(DESK_TIMEZONE).date()


def ensure_not_before(now: datetime, earlier_event_at: datetime, earlier_event: str) -> None:
    """Refuse to record an event that would be dated before the one it follows.

    This only matters when a reviewer moves the test clock backwards, e.g. checks
    an item out "next week" and then tries to return it "today".
    """
    if now < earlier_event_at:
        raise InvalidTransitionError(
            f"The current time is before this loan was {earlier_event}; "
            "move the clock forward or reset it.",
            code="CLOCK_BEFORE_PREVIOUS_EVENT",
            details={"now": now.isoformat(), f"{earlier_event}_at": earlier_event_at.isoformat()},
        )


def reservation_expires_at(reserved_at: datetime) -> datetime:
    return reserved_at + RESERVATION_HOLD


def is_reservation_expired(reserved_at: datetime, now: datetime) -> bool:
    """A reservation is valid for exactly 48 hours: at 47h59m it holds, at 48h00m it has lapsed."""
    return now >= reservation_expires_at(reserved_at)


def due_at_for(checked_out_at: datetime) -> datetime:
    return checked_out_at + LOAN_PERIOD


def is_overdue(due_at: datetime, now: datetime) -> bool:
    """Returning exactly at due_at is on time; one second later is overdue."""
    return now > due_at


def days_overdue(due_at: datetime, now: datetime) -> int:
    """Whole days late, rounding any part-day up (1 minute late counts as 1 day).

    Days are counted as 24-hour periods from due_at, which is the same in UTC and
    IST and does not depend on where the desk's midnight falls.
    """
    if not is_overdue(due_at, now):
        return 0
    late_by = now - due_at
    full_days, remainder = divmod(late_by, ONE_DAY)
    return full_days + (1 if remainder else 0)
