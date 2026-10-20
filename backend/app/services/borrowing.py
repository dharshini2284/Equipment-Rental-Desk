"""Gathers the facts the borrowing rules need and enforces them."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.eligibility import BorrowingBlock, BorrowingSnapshot, borrowing_blocks
from app.domain.errors import BusinessRuleViolation
from app.domain.statuses import MemberStatus
from app.domain.timing import days_overdue
from app.persistence import queries
from app.persistence.models import Member


def borrowing_snapshot(session: Session, member: Member, now: datetime) -> BorrowingSnapshot:
    earliest_due = queries.earliest_overdue_due_at(session, member.id, now)
    return BorrowingSnapshot(
        member_status=MemberStatus(member.status),
        balance_paise=queries.member_balance_paise(session, member.id),
        active_loan_count=queries.count_active_loans(session, member.id, now),
        worst_days_overdue=days_overdue(earliest_due, now) if earliest_due else 0,
    )


def current_blocks(
    session: Session, member: Member, now: datetime, *, for_new_reservation: bool
) -> list[BorrowingBlock]:
    snapshot = borrowing_snapshot(session, member, now)
    return borrowing_blocks(snapshot, for_new_reservation=for_new_reservation)


def ensure_member_can_borrow(
    session: Session, member: Member, now: datetime, *, for_new_reservation: bool
) -> None:
    blocks = current_blocks(session, member, now, for_new_reservation=for_new_reservation)
    if not blocks:
        return
    raise BusinessRuleViolation(
        " ".join(block.message for block in blocks),
        # The first block is the headline code; every reason is listed in details.
        code=blocks[0].code,
        details={
            "member_id": member.id,
            "blocks": [{"code": block.code, "message": block.message} for block in blocks],
        },
    )
