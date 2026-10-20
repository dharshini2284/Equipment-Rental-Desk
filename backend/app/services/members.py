"""Member records, suspension, eligibility and statements."""

import logging
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domain.errors import BusinessRuleViolation, ConflictError, InvalidTransitionError
from app.domain.statuses import LoanStatus, MemberStatus
from app.domain.timing import desk_date
from app.persistence import queries
from app.persistence.models import Member, MemberStatusChange, Notification
from app.services.borrowing import current_blocks
from app.services.notifications import Kind, notify
from app.services.views import (
    Eligibility,
    MemberDetailView,
    MemberView,
    StatementView,
    build_loan_view,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewMember:
    name: str
    phone: str
    joined_on: date | None  # None means "today at the desk"


def _ensure_phone_free(session: Session, phone: str, exclude_member_id: int | None = None) -> None:
    if queries.phone_in_use(session, phone, exclude_member_id=exclude_member_id):
        raise ConflictError(
            "Another member already uses this phone number.",
            code="PHONE_IN_USE",
            details={"phone": phone},
        )


def _ensure_join_date_not_future(joined_on: date, now: datetime) -> None:
    today = desk_date(now)
    if joined_on > today:
        raise BusinessRuleViolation(
            "Join date cannot be in the future.",
            code="JOIN_DATE_IN_FUTURE",
            details={"joined_on": joined_on.isoformat(), "today": today.isoformat()},
        )


def create_member(session: Session, *, new_member: NewMember, now: datetime) -> MemberView:
    joined_on = new_member.joined_on or desk_date(now)
    _ensure_join_date_not_future(joined_on, now)
    with session.begin():
        _ensure_phone_free(session, new_member.phone)
        member = Member(
            name=new_member.name,
            phone=new_member.phone,
            joined_on=joined_on,
            status=MemberStatus.ACTIVE,
            created_at=now,
        )
        session.add(member)
        session.flush()
        logger.info("member.created", extra={"member_id": member.id})
        return MemberView(member=member, balance_paise=0)


def update_member(
    session: Session, *, member_id: int, changes: dict[str, object], now: datetime
) -> MemberView:
    """Edit name, phone or join date. Status changes go through suspend/reinstate."""
    joined_on = changes.get("joined_on")
    if isinstance(joined_on, date):
        _ensure_join_date_not_future(joined_on, now)
    with session.begin():
        member = queries.get_member(session, member_id, for_update=True)
        if "phone" in changes:
            _ensure_phone_free(session, str(changes["phone"]), exclude_member_id=member.id)
        for field_name, value in changes.items():
            setattr(member, field_name, value)
        session.flush()
        logger.info("member.updated", extra={"member_id": member.id, "fields": sorted(changes)})
        balance = queries.member_balance_paise(session, member.id)
        return MemberView(member=member, balance_paise=balance)


def delete_member(session: Session, *, member_id: int) -> None:
    with session.begin():
        member = queries.get_member(session, member_id, for_update=True)
        if queries.member_has_history(session, member.id):
            raise ConflictError(
                f"Member {member.id} has loans or payments on record and cannot be deleted; "
                "suspend them instead.",
                code="MEMBER_HAS_HISTORY",
                details={"member_id": member.id},
            )
        for change in list(member.status_changes):
            session.delete(change)
        session.execute(delete(Notification).where(Notification.member_id == member.id))
        session.delete(member)
        logger.info("member.deleted", extra={"member_id": member_id})


def list_members(
    session: Session,
    *,
    search: str | None,
    status: MemberStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[MemberView], int]:
    with session.begin():
        members, total = queries.list_members(
            session, search=search, status=status, limit=limit, offset=offset
        )
        balances = queries.balances_for_members(session, [m.id for m in members])
        views = [MemberView(member=m, balance_paise=balances.get(m.id, 0)) for m in members]
        return views, total


def get_member_detail(session: Session, *, member_id: int, now: datetime) -> MemberDetailView:
    with session.begin():
        member = queries.get_member(session, member_id)
        blocks = current_blocks(session, member, now, for_new_reservation=True)
        return MemberDetailView(
            member=member,
            balance_paise=queries.member_balance_paise(session, member.id),
            active_loan_count=queries.count_active_loans(session, member.id, now),
            eligibility=Eligibility(can_borrow=not blocks, blocks=blocks),
            status_changes=list(member.status_changes),
        )


def _change_status(
    session: Session,
    *,
    member_id: int,
    target: MemberStatus,
    reason: str,
    now: datetime,
) -> MemberDetailView:
    with session.begin():
        member = queries.get_member(session, member_id, for_update=True)
        current = MemberStatus(member.status)
        if current == target:
            raise InvalidTransitionError(
                f"Member {member.id} is already {target.value}.",
                code=f"ALREADY_{target.value.upper()}",
                details={"member_id": member.id, "current_status": current.value},
            )
        member.status = target
        session.add(
            MemberStatusChange(
                member=member,
                from_status=current,
                to_status=target,
                reason=reason,
                changed_at=now,
            )
        )
        session.flush()
        suspended = target == MemberStatus.SUSPENDED
        notify(
            session,
            member=member,
            kind=Kind.SUSPENDED if suspended else Kind.REINSTATED,
            now=now,
            message=(
                "Your membership is suspended, so you can't borrow for now. "
                "You can still return items and pay fees."
                if suspended
                else "Your membership is active again. Welcome back!"
            ),
        )
        logger.info(
            "member.status_changed",
            extra={"member_id": member.id, "from_status": current.value, "to_status": target.value},
        )
    return get_member_detail(session, member_id=member_id, now=now)


def suspend_member(
    session: Session, *, member_id: int, reason: str, now: datetime
) -> MemberDetailView:
    return _change_status(
        session, member_id=member_id, target=MemberStatus.SUSPENDED, reason=reason, now=now
    )


def reinstate_member(
    session: Session, *, member_id: int, reason: str, now: datetime
) -> MemberDetailView:
    return _change_status(
        session, member_id=member_id, target=MemberStatus.ACTIVE, reason=reason, now=now
    )


def get_statement(session: Session, *, member_id: int, now: datetime) -> StatementView:
    with session.begin():
        member = queries.get_member(session, member_id)
        loans = [
            build_loan_view(loan, now) for loan in queries.loans_for_member(session, member.id)
        ]
        payments = queries.payments_for_member(session, member.id)
        total_fees = queries.total_fees_charged_paise(session, member.id)
        total_paid = sum(payment.amount_paise for payment in payments)
        return StatementView(
            member=member,
            balance_paise=total_fees - total_paid,
            total_fees_charged_paise=total_fees,
            total_paid_paise=total_paid,
            accrued_unbilled_fees_paise=sum(
                view.accrued_fee_paise for view in loans if view.status == LoanStatus.OVERDUE
            ),
            loans=loans,
            payments=payments,
        )
