"""Waitlist: queue for an unavailable item, and hand it to the next eligible member.

Promotion runs whenever an item becomes Available again (return, cancelled or lapsed
hold, back from maintenance). Members are tried in the order they joined; anyone who
can't borrow at that moment (suspended, fees over ₹100, a long-overdue loan, already
at 3 active loans) is skipped with the reason recorded, and the next member is tried.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.errors import InvalidTransitionError
from app.domain.statuses import ItemStatus, WaitlistStatus
from app.domain.waitlist import ensure_can_join_waitlist
from app.persistence import queries
from app.persistence.models import Item, Loan, WaitlistEntry
from app.services.borrowing import current_blocks, ensure_member_can_borrow
from app.services.holds import create_reservation, live_item_status, settle_lapsed_reservation
from app.services.notifications import Kind, notify

logger = logging.getLogger(__name__)

MAX_NOTE_LENGTH = 300


@dataclass(frozen=True)
class WaitlistEntryView:
    entry: WaitlistEntry
    # Place in the live queue; None once the entry is resolved.
    position: int | None


def _view(session: Session, entry: WaitlistEntry) -> WaitlistEntryView:
    waiting = entry.status == WaitlistStatus.WAITING
    return WaitlistEntryView(
        entry=entry, position=queries.waiting_position(session, entry) if waiting else None
    )


def promote_next_in_line(session: Session, item: Item, now: datetime) -> Loan | None:
    """Reserve the item for the first eligible waiting member. Caller holds the item lock.

    Only call this when the item is Available with no open loan.
    """
    for entry in queries.waiting_entries_for_item(session, item.id):
        # Locked so the member's active-loan count can't change under us. This takes a
        # member lock after the item lock (the reverse of the usual order); PostgreSQL
        # resolves the rare resulting deadlock by aborting one transaction (503, retry).
        member = queries.get_member(session, entry.member_id, for_update=True)
        blocks = current_blocks(session, member, now, for_new_reservation=True)
        entry.resolved_at = now
        if blocks:
            reasons = " ".join(block.message for block in blocks)
            entry.status = WaitlistStatus.SKIPPED
            entry.note = reasons[:MAX_NOTE_LENGTH]
            notify(
                session,
                member=member,
                kind=Kind.WAITLIST_SKIPPED,
                now=now,
                message=(
                    f"{item.name} became available but could not be reserved for you: "
                    f"{reasons} You have been removed from its waitlist."
                ),
            )
            logger.info(
                "waitlist.skipped",
                extra={"waitlist_entry_id": entry.id, "member_id": member.id, "item_id": item.id},
            )
            continue

        loan = create_reservation(session, member=member, item=item, now=now, from_waitlist=True)
        entry.status = WaitlistStatus.FULFILLED
        entry.loan_id = loan.id
        session.flush()
        logger.info(
            "waitlist.fulfilled",
            extra={
                "waitlist_entry_id": entry.id,
                "member_id": member.id,
                "item_id": item.id,
                "loan_id": loan.id,
            },
        )
        return loan
    return None


def hand_lapsed_hold_to_queue(session: Session, *, item_id: int, now: datetime) -> Loan | None:
    """Close a lapsed hold and reserve the item for the next in line, in its own transaction.

    Callers run this *before* their own transaction, so the queue's turn is committed even
    if the caller's request is then refused (e.g. a walk-up reservation for that item).
    Returns the reservation made for the queue, if any.
    """
    with session.begin():
        item = queries.get_item(session, item_id, for_update=True)
        open_loan = settle_lapsed_reservation(session, item, now)
        if open_loan is None and item.status == ItemStatus.AVAILABLE:
            return promote_next_in_line(session, item, now)
        return None


def join_waitlist(
    session: Session, *, member_id: int, item_id: int, now: datetime
) -> WaitlistEntryView:
    # A lapsed hold goes to the queue before anyone new joins it.
    hand_lapsed_hold_to_queue(session, item_id=item_id, now=now)
    with session.begin():
        member = queries.get_member(session, member_id, for_update=True)
        item = queries.get_item(session, item_id, for_update=True)
        open_loan = queries.find_open_loan_for_item(session, item.id)

        ensure_can_join_waitlist(
            live_item_status(item, open_loan, now),
            item_id=item.id,
            member_id=member.id,
            already_waiting=queries.is_waiting(session, item.id, member.id),
            holds_item=open_loan is not None and open_loan.member_id == member.id,
        )
        # The active-loan limit is checked when the member's turn comes, not now.
        ensure_member_can_borrow(session, member, now, for_new_reservation=False)

        entry = WaitlistEntry(
            item=item, member=member, status=WaitlistStatus.WAITING, joined_at=now, note=""
        )
        session.add(entry)
        session.flush()
        view = _view(session, entry)
        notify(
            session,
            member=member,
            kind=Kind.WAITLIST_JOINED,
            now=now,
            message=(
                f"You are number {view.position} in line for {item.name}. "
                "We will text you when it is reserved for you."
            ),
        )
        logger.info(
            "waitlist.joined",
            extra={"waitlist_entry_id": entry.id, "member_id": member.id, "item_id": item.id},
        )
        return view


def leave_waitlist(session: Session, *, entry_id: int, now: datetime) -> WaitlistEntryView:
    with session.begin():
        entry = queries.get_waitlist_entry(session, entry_id, for_update=True)
        if entry.status != WaitlistStatus.WAITING:
            raise InvalidTransitionError(
                f"Waitlist entry {entry.id} is already {entry.status}.",
                details={"waitlist_entry_id": entry.id, "current_status": entry.status},
            )
        entry.status = WaitlistStatus.CANCELLED
        entry.resolved_at = now
        session.flush()
        logger.info(
            "waitlist.left",
            extra={"waitlist_entry_id": entry.id, "member_id": entry.member_id},
        )
        return _view(session, entry)


def list_waitlist(
    session: Session,
    *,
    item_id: int | None,
    member_id: int | None,
    status: WaitlistStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[WaitlistEntryView], int]:
    with session.begin():
        entries, total = queries.list_waitlist_entries(
            session, item_id=item_id, member_id=member_id, status=status, limit=limit, offset=offset
        )
        return [_view(session, entry) for entry in entries], total
