"""Read models returned by the services: ORM rows plus the values derived from the clock."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.eligibility import BorrowingBlock
from app.domain.fees import late_fee_paise
from app.domain.item_state import allowed_actions, effective_item_status, effective_loan_status
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus
from app.domain.timing import days_overdue, reservation_expires_at
from app.persistence.models import Item, Loan, Member, MemberStatusChange, Payment


@dataclass(frozen=True)
class LoanView:
    loan: Loan
    status: LoanStatus
    reservation_expires_at: datetime
    days_overdue: int
    # What the fee would be if the item came back right now; 0 unless overdue.
    accrued_fee_paise: int


@dataclass(frozen=True)
class ItemView:
    item: Item
    status: ItemStatus
    allowed_actions: tuple[ItemAction, ...]
    current_loan: LoanView | None


@dataclass(frozen=True)
class MemberView:
    member: Member
    balance_paise: int


@dataclass(frozen=True)
class Eligibility:
    can_borrow: bool
    blocks: list[BorrowingBlock]


@dataclass(frozen=True)
class MemberDetailView:
    member: Member
    balance_paise: int
    active_loan_count: int
    eligibility: Eligibility
    status_changes: list[MemberStatusChange]


@dataclass(frozen=True)
class StatementView:
    member: Member
    balance_paise: int
    total_fees_charged_paise: int
    total_paid_paise: int
    accrued_unbilled_fees_paise: int
    loans: list[LoanView]
    payments: list[Payment]


def build_loan_view(loan: Loan, now: datetime) -> LoanView:
    status = effective_loan_status(LoanStatus(loan.status), loan.reserved_at, loan.due_at, now)
    overdue_days = 0
    accrued_fee = 0
    if status == LoanStatus.OVERDUE and loan.due_at is not None:
        overdue_days = days_overdue(loan.due_at, now)
        accrued_fee = late_fee_paise(loan.due_at, now, loan.item.replacement_value_paise)
    return LoanView(
        loan=loan,
        status=status,
        reservation_expires_at=reservation_expires_at(loan.reserved_at),
        days_overdue=overdue_days,
        accrued_fee_paise=accrued_fee,
    )


def build_item_view(item: Item, open_loan: Loan | None, now: datetime) -> ItemView:
    status = effective_item_status(
        ItemStatus(item.status),
        open_loan.reserved_at if open_loan else None,
        open_loan.due_at if open_loan else None,
        now,
    )
    current_loan = None
    if open_loan is not None:
        loan_view = build_loan_view(open_loan, now)
        # A lapsed reservation no longer holds the item, so it is not shown as current.
        if loan_view.status != LoanStatus.EXPIRED:
            current_loan = loan_view
    return ItemView(
        item=item,
        status=status,
        allowed_actions=allowed_actions(status),
        current_loan=current_loan,
    )
