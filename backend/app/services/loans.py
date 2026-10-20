"""Reserve, check out, return and cancel."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.fees import late_fee_paise
from app.domain.item_state import (
    effective_loan_status,
    ensure_action_allowed,
    ensure_loan_action_allowed,
)
from app.domain.money import format_rupees
from app.domain.policy import LATE_FEE_PER_DAY_PAISE
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus
from app.domain.timing import due_at_for, ensure_not_before
from app.persistence import queries
from app.persistence.models import Item, Loan, Member
from app.services.borrowing import ensure_member_can_borrow
from app.services.holds import create_reservation, live_item_status, settle_lapsed_reservation
from app.services.notifications import Kind, format_ist, notify
from app.services.views import LoanView, build_loan_view
from app.services.waitlist import hand_lapsed_hold_to_queue, promote_next_in_line

logger = logging.getLogger(__name__)


def _lock_loan_with_parties(session: Session, loan_id: int) -> tuple[Loan, Member, Item]:
    """Lock member, item and loan in the standard order and return them fresh."""
    loan = queries.get_loan(session, loan_id)
    member = queries.get_member(session, loan.member_id, for_update=True)
    item = queries.get_item(session, loan.item_id, for_update=True)
    loan = queries.get_loan(session, loan_id, for_update=True)
    return loan, member, item


def _loan_status(loan: Loan, now: datetime) -> LoanStatus:
    return effective_loan_status(LoanStatus(loan.status), loan.reserved_at, loan.due_at, now)


def reserve_item(session: Session, *, member_id: int, item_id: int, now: datetime) -> LoanView:
    # A lapsed hold goes to the waitlist before a walk-up request, and that stays committed
    # even if this request is then refused.
    reserved_for_queue = hand_lapsed_hold_to_queue(session, item_id=item_id, now=now)
    with session.begin():
        member = queries.get_member(session, member_id, for_update=True)
        item = queries.get_item(session, item_id, for_update=True)
        open_loan = settle_lapsed_reservation(session, item, now)
        if reserved_for_queue is not None and reserved_for_queue.member_id == member.id:
            # The requester was first in line and already holds it.
            return build_loan_view(queries.get_loan(session, reserved_for_queue.id), now)

        ensure_action_allowed(
            live_item_status(item, open_loan, now), ItemAction.RESERVE, item_id=item.id
        )
        ensure_member_can_borrow(session, member, now, for_new_reservation=True)
        loan = create_reservation(session, member=member, item=item, now=now)
        return build_loan_view(loan, now)


def check_out(session: Session, *, loan_id: int, now: datetime) -> LoanView:
    with session.begin():
        loan, member, item = _lock_loan_with_parties(session, loan_id)
        ensure_loan_action_allowed(loan.id, _loan_status(loan, now), ItemAction.CHECK_OUT)
        ensure_not_before(now, loan.reserved_at, "reserved")
        ensure_member_can_borrow(session, member, now, for_new_reservation=False)

        loan.status = LoanStatus.CHECKED_OUT
        loan.checked_out_at = now
        loan.due_at = due_at_for(now)
        item.status = ItemStatus.CHECKED_OUT
        item.updated_at = now
        session.flush()
        logger.info(
            "loan.checked_out",
            extra={"loan_id": loan.id, "member_id": member.id, "item_id": item.id},
        )
        notify(
            session,
            member=member,
            kind=Kind.CHECKED_OUT,
            loan_id=loan.id,
            now=now,
            message=(
                f"You have {item.name}. Please return it by {format_ist(loan.due_at)}. "
                f"Late returns cost {format_rupees(LATE_FEE_PER_DAY_PAISE)} a day."
            ),
        )
        return build_loan_view(loan, now)


def return_item(
    session: Session,
    *,
    loan_id: int,
    now: datetime,
    send_to_maintenance: bool = False,
    condition_note: str | None = None,
) -> LoanView:
    """Close a checked-out loan, charge any late fee, and free (or quarantine) the item.

    Suspended members can still return items; blocking returns would only keep
    the tool away from the library longer.
    """
    with session.begin():
        loan, member, item = _lock_loan_with_parties(session, loan_id)
        ensure_loan_action_allowed(loan.id, _loan_status(loan, now), ItemAction.RETURN)
        assert loan.checked_out_at is not None and loan.due_at is not None  # guaranteed by status
        ensure_not_before(now, loan.checked_out_at, "checked_out")

        fee = late_fee_paise(loan.due_at, now, item.replacement_value_paise)
        loan.status = LoanStatus.RETURNED
        loan.returned_at = now
        loan.fee_charged_paise = fee
        item.status = ItemStatus.MAINTENANCE if send_to_maintenance else ItemStatus.AVAILABLE
        if condition_note is not None:
            item.condition_note = condition_note
        item.updated_at = now
        session.flush()
        logger.info(
            "loan.returned",
            extra={
                "loan_id": loan.id,
                "member_id": member.id,
                "item_id": item.id,
                "fee_charged_paise": fee,
                "sent_to_maintenance": send_to_maintenance,
            },
        )
        _notify_returned(session, member=member, item=item, loan=loan, now=now)
        view = build_loan_view(loan, now)
        if not send_to_maintenance:
            promote_next_in_line(session, item, now)
        return view


def cancel_reservation(session: Session, *, loan_id: int, now: datetime) -> LoanView:
    with session.begin():
        loan, member, item = _lock_loan_with_parties(session, loan_id)
        ensure_loan_action_allowed(loan.id, _loan_status(loan, now), ItemAction.CANCEL_RESERVATION)
        ensure_not_before(now, loan.reserved_at, "reserved")

        loan.status = LoanStatus.CANCELLED
        loan.cancelled_at = now
        item.status = ItemStatus.AVAILABLE
        item.updated_at = now
        session.flush()
        logger.info(
            "loan.cancelled",
            extra={"loan_id": loan.id, "member_id": member.id, "item_id": item.id},
        )
        notify(
            session,
            member=member,
            kind=Kind.RESERVATION_CANCELLED,
            loan_id=loan.id,
            now=now,
            message=f"Your reservation for {item.name} has been cancelled.",
        )
        view = build_loan_view(loan, now)
        promote_next_in_line(session, item, now)
        return view


def _notify_returned(
    session: Session, *, member: Member, item: Item, loan: Loan, now: datetime
) -> None:
    fee = loan.fee_charged_paise or 0
    if fee:
        balance = queries.member_balance_paise(session, member.id)
        message = (
            f"Thanks for returning {item.name}. A late fee of {format_rupees(fee)} was added; "
            f"you now owe {format_rupees(balance)}."
        )
    else:
        message = f"Thanks for returning {item.name} on time."
    notify(session, member=member, kind=Kind.RETURNED, loan_id=loan.id, now=now, message=message)


def get_loan(session: Session, *, loan_id: int, now: datetime) -> LoanView:
    with session.begin():
        return build_loan_view(queries.get_loan(session, loan_id), now)


def list_loans(
    session: Session,
    *,
    now: datetime,
    member_id: int | None,
    item_id: int | None,
    limit: int,
    offset: int,
) -> tuple[list[LoanView], int]:
    with session.begin():
        loans, total = queries.list_loans(
            session, member_id=member_id, item_id=item_id, limit=limit, offset=offset
        )
        return [build_loan_view(loan, now) for loan in loans], total


def list_overdue_loans(
    session: Session, *, now: datetime, limit: int, offset: int
) -> tuple[list[LoanView], int]:
    with session.begin():
        loans, total = queries.list_overdue_loans(session, now=now, limit=limit, offset=offset)
        return [build_loan_view(loan, now) for loan in loans], total
