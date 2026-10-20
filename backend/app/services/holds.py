"""Low-level helpers shared by loans, items and the waitlist.

None of these open a transaction; callers hold the item's row lock while using them.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.item_state import effective_item_status
from app.domain.statuses import ItemStatus, LoanStatus
from app.domain.timing import is_reservation_expired, reservation_expires_at
from app.persistence import queries
from app.persistence.models import Item, Loan, Member
from app.services.notifications import Kind, format_ist, notify

logger = logging.getLogger(__name__)


def settle_lapsed_reservation(session: Session, item: Item, now: datetime) -> Loan | None:
    """Write-time half of reservation expiry: close a lapsed hold before acting on the item.

    Returns the loan that still holds the item, or None if it is free.
    The read-time half is ``effective_item_status``, which hides lapsed holds without writing.
    """
    open_loan = queries.find_open_loan_for_item(session, item.id)
    if (
        open_loan is not None
        and open_loan.status == LoanStatus.RESERVED
        and is_reservation_expired(open_loan.reserved_at, now)
    ):
        open_loan.status = LoanStatus.EXPIRED
        item.status = ItemStatus.AVAILABLE
        item.updated_at = now
        session.flush()
        logger.info(
            "reservation.expired",
            extra={"loan_id": open_loan.id, "item_id": item.id, "member_id": open_loan.member_id},
        )
        return None
    return open_loan


def live_item_status(item: Item, open_loan: Loan | None, now: datetime) -> ItemStatus:
    return effective_item_status(
        ItemStatus(item.status),
        open_loan.reserved_at if open_loan else None,
        open_loan.due_at if open_loan else None,
        now,
    )


def create_reservation(
    session: Session, *, member: Member, item: Item, now: datetime, from_waitlist: bool = False
) -> Loan:
    """Hold the item for the member for 48 hours. Rules must already have been checked."""
    loan = Loan(member=member, item=item, status=LoanStatus.RESERVED, reserved_at=now)
    item.status = ItemStatus.RESERVED
    item.updated_at = now
    session.add(loan)
    session.flush()
    logger.info(
        "loan.reserved", extra={"loan_id": loan.id, "member_id": member.id, "item_id": item.id}
    )
    until = format_ist(reservation_expires_at(now))
    notify(
        session,
        member=member,
        kind=Kind.WAITLIST_RESERVED if from_waitlist else Kind.RESERVED,
        loan_id=loan.id,
        now=now,
        message=(
            f"Good news: {item.name}, which you were waiting for, is reserved for you until "
            f"{until}. Collect it before then."
            if from_waitlist
            else f"{item.name} is reserved for you until {until}. Collect it before then."
        ),
    )
    return loan
