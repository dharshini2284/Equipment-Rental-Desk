"""Who may borrow: suspension, unpaid fees, long-overdue loans and the active-loan limit."""

from dataclasses import dataclass

from app.domain.money import format_rupees as _rupees
from app.domain.policy import (
    MAX_ACTIVE_LOANS,
    MAX_DAYS_OVERDUE_BEFORE_BLOCK,
    MAX_UNPAID_BALANCE_PAISE,
)
from app.domain.statuses import MemberStatus


@dataclass(frozen=True)
class BorrowingSnapshot:
    """The facts about a member that the borrowing rules need, gathered at one instant."""

    member_status: MemberStatus
    balance_paise: int
    active_loan_count: int
    worst_days_overdue: int


@dataclass(frozen=True)
class BorrowingBlock:
    code: str
    message: str


def borrowing_blocks(
    snapshot: BorrowingSnapshot, *, for_new_reservation: bool
) -> list[BorrowingBlock]:
    """Every reason the member cannot borrow right now (empty list means they can).

    The active-loan limit only applies when creating a new reservation: checking
    out an existing reservation does not change how many active loans exist.
    """
    blocks: list[BorrowingBlock] = []

    if snapshot.member_status == MemberStatus.SUSPENDED:
        blocks.append(BorrowingBlock("MEMBER_SUSPENDED", "Member is suspended."))

    if snapshot.balance_paise > MAX_UNPAID_BALANCE_PAISE:
        blocks.append(
            BorrowingBlock(
                "FEE_BALANCE_OVER_LIMIT",
                f"Unpaid fees of {_rupees(snapshot.balance_paise)} exceed the "
                f"{_rupees(MAX_UNPAID_BALANCE_PAISE)} limit.",
            )
        )

    if snapshot.worst_days_overdue > MAX_DAYS_OVERDUE_BEFORE_BLOCK:
        blocks.append(
            BorrowingBlock(
                "LOAN_OVERDUE_TOO_LONG",
                f"A loan is {snapshot.worst_days_overdue} days overdue "
                f"(more than {MAX_DAYS_OVERDUE_BEFORE_BLOCK} days).",
            )
        )

    if for_new_reservation and snapshot.active_loan_count >= MAX_ACTIVE_LOANS:
        blocks.append(
            BorrowingBlock(
                "ACTIVE_LOAN_LIMIT_REACHED",
                f"Member already has {snapshot.active_loan_count} active loans "
                f"(limit {MAX_ACTIVE_LOANS}).",
            )
        )

    return blocks
