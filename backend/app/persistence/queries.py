"""Read and lookup queries used by the services.

Every query goes through SQLAlchemy expressions, so user input is always sent as
bound parameters. Functions take ``now`` explicitly wherever the answer depends
on the clock, because "reserved" and "overdue" are derived from time.
"""

from datetime import datetime
from typing import TypeVar

from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.domain.errors import NotFoundError
from app.domain.policy import RESERVATION_HOLD
from app.domain.statuses import ItemStatus, LoanStatus, MemberStatus, WaitlistStatus
from app.persistence.models import Base, Item, Loan, Member, Payment, WaitlistEntry

ModelT = TypeVar("ModelT", bound=Base)


def _get_or_404(
    session: Session, model: type[ModelT], entity_id: int, label: str, for_update: bool
) -> ModelT:
    statement = select(model).where(model.id == entity_id)  # type: ignore[attr-defined]
    if for_update:
        # populate_existing makes sure we act on the row as it is once the lock is held,
        # not a copy cached earlier in the same session.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    entity = session.scalars(statement).one_or_none()
    if entity is None:
        raise NotFoundError(
            f"{label} {entity_id} not found.", details={f"{label.lower()}_id": entity_id}
        )
    return entity


def get_member(session: Session, member_id: int, *, for_update: bool = False) -> Member:
    return _get_or_404(session, Member, member_id, "Member", for_update)


def get_item(session: Session, item_id: int, *, for_update: bool = False) -> Item:
    return _get_or_404(session, Item, item_id, "Item", for_update)


def get_loan(session: Session, loan_id: int, *, for_update: bool = False) -> Loan:
    return _get_or_404(session, Loan, loan_id, "Loan", for_update)


def get_waitlist_entry(
    session: Session, entry_id: int, *, for_update: bool = False
) -> WaitlistEntry:
    return _get_or_404(session, WaitlistEntry, entry_id, "Waitlist entry", for_update)


def phone_in_use(session: Session, phone: str, *, exclude_member_id: int | None = None) -> bool:
    condition = Member.phone == phone
    if exclude_member_id is not None:
        condition = and_(condition, Member.id != exclude_member_id)
    return bool(session.scalar(select(exists().where(condition))))


def find_open_loan_for_item(session: Session, item_id: int) -> Loan | None:
    """The loan currently holding the item (reserved or checked out), if any."""
    return session.scalars(
        select(Loan)
        .options(joinedload(Loan.member))
        .where(Loan.item_id == item_id, Loan.status.in_(_open_statuses()))
    ).one_or_none()


def _open_statuses() -> list[str]:
    return [LoanStatus.RESERVED.value, LoanStatus.CHECKED_OUT.value]


# --- Member money and borrowing facts -------------------------------------------------


def _fees_charged_subquery():  # type: ignore[no-untyped-def]
    return (
        select(Loan.member_id, func.sum(Loan.fee_charged_paise).label("fees"))
        .where(Loan.fee_charged_paise.is_not(None))
        .group_by(Loan.member_id)
        .subquery()
    )


def _payments_subquery():  # type: ignore[no-untyped-def]
    return (
        select(Payment.member_id, func.sum(Payment.amount_paise).label("paid"))
        .group_by(Payment.member_id)
        .subquery()
    )


def balances_for_members(session: Session, member_ids: list[int]) -> dict[int, int]:
    """Unpaid fee balance (fees charged on returns minus payments) per member, in paise."""
    if not member_ids:
        return {}
    fees = _fees_charged_subquery()
    paid = _payments_subquery()
    rows = session.execute(
        select(
            Member.id,
            func.coalesce(fees.c.fees, 0) - func.coalesce(paid.c.paid, 0),
        )
        .outerjoin(fees, fees.c.member_id == Member.id)
        .outerjoin(paid, paid.c.member_id == Member.id)
        .where(Member.id.in_(member_ids))
    ).all()
    return {member_id: int(balance) for member_id, balance in rows}


def member_balance_paise(session: Session, member_id: int) -> int:
    return balances_for_members(session, [member_id]).get(member_id, 0)


def total_fees_charged_paise(session: Session, member_id: int) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(Loan.fee_charged_paise), 0)).where(
            Loan.member_id == member_id
        )
    )
    return int(total or 0)


def _active_loan_condition(now: datetime):  # type: ignore[no-untyped-def]
    """Reserved (and not yet lapsed) or checked out, which includes overdue."""
    return or_(
        and_(Loan.status == LoanStatus.RESERVED.value, Loan.reserved_at > now - RESERVATION_HOLD),
        Loan.status == LoanStatus.CHECKED_OUT.value,
    )


def count_active_loans(session: Session, member_id: int, now: datetime) -> int:
    count = session.scalar(
        select(func.count(Loan.id)).where(Loan.member_id == member_id, _active_loan_condition(now))
    )
    return int(count or 0)


def earliest_overdue_due_at(session: Session, member_id: int, now: datetime) -> datetime | None:
    """due_at of the member's most overdue checked-out loan, or None if nothing is overdue."""
    return session.scalar(
        select(func.min(Loan.due_at)).where(
            Loan.member_id == member_id,
            Loan.status == LoanStatus.CHECKED_OUT.value,
            Loan.due_at < now,
        )
    )


def member_has_history(session: Session, member_id: int) -> bool:
    """Loans, payments or waitlist entries: anything a statement or queue refers to."""
    return any(
        session.scalar(select(exists().where(column == member_id)))
        for column in (Loan.member_id, Payment.member_id, WaitlistEntry.member_id)
    )


def item_has_history(session: Session, item_id: int) -> bool:
    return any(
        session.scalar(select(exists().where(column == item_id)))
        for column in (Loan.item_id, WaitlistEntry.item_id)
    )


# --- Waitlist --------------------------------------------------------------------------


def waiting_entries_for_item(session: Session, item_id: int) -> list[WaitlistEntry]:
    """The live queue for an item, first in line first."""
    return list(
        session.scalars(
            select(WaitlistEntry)
            .where(
                WaitlistEntry.item_id == item_id,
                WaitlistEntry.status == WaitlistStatus.WAITING.value,
            )
            .order_by(WaitlistEntry.joined_at, WaitlistEntry.id)
        )
    )


def is_waiting(session: Session, item_id: int, member_id: int) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    WaitlistEntry.item_id == item_id,
                    WaitlistEntry.member_id == member_id,
                    WaitlistEntry.status == WaitlistStatus.WAITING.value,
                )
            )
        )
    )


def list_waitlist_entries(
    session: Session,
    *,
    item_id: int | None,
    member_id: int | None,
    status: WaitlistStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[WaitlistEntry], int]:
    statement = (
        select(WaitlistEntry)
        .options(joinedload(WaitlistEntry.member), joinedload(WaitlistEntry.item))
        .order_by(WaitlistEntry.joined_at, WaitlistEntry.id)
    )
    if item_id is not None:
        statement = statement.where(WaitlistEntry.item_id == item_id)
    if member_id is not None:
        statement = statement.where(WaitlistEntry.member_id == member_id)
    if status is not None:
        statement = statement.where(WaitlistEntry.status == status.value)
    rows, total = paginate(session, statement, limit, offset)
    return [row[0] for row in rows], total


def waiting_position(session: Session, entry: WaitlistEntry) -> int:
    """1-based place in the item's live queue."""
    ahead = session.scalar(
        select(func.count(WaitlistEntry.id)).where(
            WaitlistEntry.item_id == entry.item_id,
            WaitlistEntry.status == WaitlistStatus.WAITING.value,
            or_(
                WaitlistEntry.joined_at < entry.joined_at,
                and_(WaitlistEntry.joined_at == entry.joined_at, WaitlistEntry.id < entry.id),
            ),
        )
    )
    return int(ahead or 0) + 1


# --- Lists -----------------------------------------------------------------------------


def paginate(session: Session, statement: Select, limit: int, offset: int):  # type: ignore[no-untyped-def]
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = session.execute(statement.limit(limit).offset(offset)).all()
    return rows, int(total or 0)


def list_members(
    session: Session,
    *,
    search: str | None,
    status: MemberStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[Member], int]:
    statement = select(Member).order_by(Member.name, Member.id)
    if search:
        statement = statement.where(
            or_(
                Member.name.icontains(search, autoescape=True),
                Member.phone.contains(search, autoescape=True),
            )
        )
    if status is not None:
        statement = statement.where(Member.status == status.value)
    rows, total = paginate(session, statement, limit, offset)
    return [row[0] for row in rows], total


def effective_item_status_expression(now: datetime):  # type: ignore[no-untyped-def]
    """SQL twin of ``domain.item_state.effective_item_status`` so lists can filter by it.

    Must be used with the open loan outer-joined to the item.
    """
    return case(
        (
            and_(
                Item.status == ItemStatus.RESERVED.value,
                Loan.reserved_at <= now - RESERVATION_HOLD,
            ),
            ItemStatus.AVAILABLE.value,
        ),
        (
            and_(Item.status == ItemStatus.CHECKED_OUT.value, Loan.due_at < now),
            ItemStatus.OVERDUE.value,
        ),
        else_=Item.status,
    )


def list_items(
    session: Session,
    *,
    now: datetime,
    status: ItemStatus | None,
    search: str | None,
    category: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Item, Loan | None]], int]:
    """Items with their open loan (if any), filtered on the clock-derived status."""
    effective_status = effective_item_status_expression(now)
    statement = (
        select(Item, Loan)
        .outerjoin(Loan, and_(Loan.item_id == Item.id, Loan.status.in_(_open_statuses())))
        .order_by(Item.name, Item.id)
    )
    if status is not None:
        statement = statement.where(effective_status == status.value)
    if search:
        statement = statement.where(
            or_(
                Item.name.icontains(search, autoescape=True),
                Item.category.icontains(search, autoescape=True),
            )
        )
    if category:
        statement = statement.where(func.lower(Item.category) == category.lower())
    rows, total = paginate(session, statement, limit, offset)
    return [(row[0], row[1]) for row in rows], total


def list_categories(session: Session) -> list[str]:
    return list(session.scalars(select(Item.category).distinct().order_by(Item.category)))


def list_loans(
    session: Session,
    *,
    member_id: int | None,
    item_id: int | None,
    limit: int,
    offset: int,
) -> tuple[list[Loan], int]:
    statement = (
        select(Loan)
        .options(joinedload(Loan.member), joinedload(Loan.item))
        .order_by(Loan.reserved_at.desc(), Loan.id.desc())
    )
    if member_id is not None:
        statement = statement.where(Loan.member_id == member_id)
    if item_id is not None:
        statement = statement.where(Loan.item_id == item_id)
    rows, total = paginate(session, statement, limit, offset)
    return [row[0] for row in rows], total


def list_overdue_loans(
    session: Session, *, now: datetime, limit: int, offset: int
) -> tuple[list[Loan], int]:
    """Checked-out loans past due, most overdue first."""
    statement = (
        select(Loan)
        .options(joinedload(Loan.member), joinedload(Loan.item))
        .where(Loan.status == LoanStatus.CHECKED_OUT.value, Loan.due_at < now)
        .order_by(Loan.due_at, Loan.id)
    )
    rows, total = paginate(session, statement, limit, offset)
    return [row[0] for row in rows], total


def loans_for_member(session: Session, member_id: int) -> list[Loan]:
    return list(
        session.scalars(
            select(Loan)
            .options(joinedload(Loan.item), joinedload(Loan.member))
            .where(Loan.member_id == member_id)
            .order_by(Loan.reserved_at.desc(), Loan.id.desc())
        )
    )


def payments_for_member(session: Session, member_id: int) -> list[Payment]:
    return list(
        session.scalars(
            select(Payment)
            .where(Payment.member_id == member_id)
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
        )
    )
