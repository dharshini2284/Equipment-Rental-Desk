"""The SMS outbox (delivery is a stub).

`notify` never opens its own transaction: it is called inside the transaction of the
action it describes, so a message is stored exactly when that action commits and
vanishes with it on rollback. A real SMS gateway would read unsent rows from this table.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, joinedload

from app.domain.money import format_rupees
from app.domain.policy import DESK_TIMEZONE, LATE_FEE_PER_DAY_PAISE
from app.domain.statuses import LoanStatus
from app.domain.timing import days_overdue
from app.persistence.models import Loan, Member, Notification
from app.persistence.queries import paginate

logger = logging.getLogger(__name__)

SENDER = "Rental Desk"
# One overdue reminder per loan per day, however often the desk presses the button.
REMINDER_INTERVAL = timedelta(hours=24)


class Kind:
    RESERVED = "reservation_created"
    RESERVATION_CANCELLED = "reservation_cancelled"
    CHECKED_OUT = "checked_out"
    RETURNED = "returned"
    WAITLIST_JOINED = "waitlist_joined"
    WAITLIST_RESERVED = "waitlist_reserved"
    WAITLIST_SKIPPED = "waitlist_skipped"
    PAYMENT_RECEIVED = "payment_received"
    SUSPENDED = "member_suspended"
    REINSTATED = "member_reinstated"
    OVERDUE_REMINDER = "overdue_reminder"


def format_ist(moment: datetime) -> str:
    return moment.astimezone(DESK_TIMEZONE).strftime("%d %b %Y, %H:%M IST")


def notify(
    session: Session,
    *,
    member: Member,
    kind: str,
    message: str,
    now: datetime,
    loan_id: int | None = None,
) -> Notification:
    notification = Notification(
        member_id=member.id,
        loan_id=loan_id,
        kind=kind,
        channel="sms",
        recipient=member.phone,
        message=f"{SENDER}: {message}",
        created_at=now,
    )
    session.add(notification)
    session.flush()
    # The message text is not logged: it contains the member's name and dues.
    logger.info(
        "notification.queued",
        extra={"notification_id": notification.id, "member_id": member.id, "kind": kind},
    )
    return notification


def list_notifications(
    session: Session, *, member_id: int | None, kind: str | None, limit: int, offset: int
) -> tuple[list[Notification], int]:
    with session.begin():
        statement = (
            select(Notification)
            .options(joinedload(Notification.member))
            .order_by(Notification.created_at.desc(), Notification.id.desc())
        )
        if member_id is not None:
            statement = statement.where(Notification.member_id == member_id)
        if kind:
            statement = statement.where(Notification.kind == kind)
        rows, total = paginate(session, statement, limit, offset)
        return [row[0] for row in rows], total


def send_overdue_reminders(session: Session, *, now: datetime) -> tuple[int, int]:
    """Queue a reminder for every overdue loan not reminded in the last 24 hours.

    Returns (queued, skipped). Safe to press repeatedly: that is what the 24-hour
    window is for.
    """
    with session.begin():
        overdue = session.scalars(
            select(Loan)
            .options(joinedload(Loan.member), joinedload(Loan.item))
            .where(Loan.status == LoanStatus.CHECKED_OUT.value, Loan.due_at < now)
            .order_by(Loan.due_at)
        ).all()
        queued = skipped = 0
        for loan in overdue:
            reminded_recently = session.scalar(
                select(
                    exists().where(
                        Notification.loan_id == loan.id,
                        Notification.kind == Kind.OVERDUE_REMINDER,
                        Notification.created_at > now - REMINDER_INTERVAL,
                    )
                )
            )
            if reminded_recently:
                skipped += 1
                continue
            assert loan.due_at is not None  # checked-out loans always have one
            notify(
                session,
                member=loan.member,
                kind=Kind.OVERDUE_REMINDER,
                loan_id=loan.id,
                now=now,
                message=(
                    f"{loan.item.name} was due {format_ist(loan.due_at)} and is "
                    f"{days_overdue(loan.due_at, now)} days late. Late fees are "
                    f"{format_rupees(LATE_FEE_PER_DAY_PAISE)} a day. Please return it."
                ),
            )
            queued += 1
        logger.info("notification.overdue_reminders", extra={"queued": queued, "skipped": skipped})
        return queued, skipped
