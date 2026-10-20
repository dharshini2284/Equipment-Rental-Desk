from app.domain.eligibility import BorrowingSnapshot, borrowing_blocks
from app.domain.statuses import MemberStatus


def snapshot(
    *,
    status: MemberStatus = MemberStatus.ACTIVE,
    balance_paise: int = 0,
    active_loans: int = 0,
    worst_days_overdue: int = 0,
) -> BorrowingSnapshot:
    return BorrowingSnapshot(
        member_status=status,
        balance_paise=balance_paise,
        active_loan_count=active_loans,
        worst_days_overdue=worst_days_overdue,
    )


def codes(snap: BorrowingSnapshot, *, for_new_reservation: bool = True) -> list[str]:
    return [b.code for b in borrowing_blocks(snap, for_new_reservation=for_new_reservation)]


def test_clean_member_can_borrow() -> None:
    assert codes(snapshot()) == []


class TestFeeBalance:
    def test_exactly_100_rupees_is_allowed(self) -> None:
        assert codes(snapshot(balance_paise=10_000)) == []

    def test_one_paisa_over_100_rupees_is_blocked(self) -> None:
        assert codes(snapshot(balance_paise=10_001)) == ["FEE_BALANCE_OVER_LIMIT"]

    def test_block_message_shows_rupees(self) -> None:
        [block] = borrowing_blocks(snapshot(balance_paise=12_050), for_new_reservation=True)
        assert "₹120.50" in block.message


class TestOverdueBlock:
    def test_overdue_14_days_is_allowed(self) -> None:
        assert codes(snapshot(worst_days_overdue=14)) == []

    def test_overdue_15_days_is_blocked(self) -> None:
        assert codes(snapshot(worst_days_overdue=15)) == ["LOAN_OVERDUE_TOO_LONG"]


class TestActiveLoanLimit:
    def test_two_active_loans_may_reserve_a_third(self) -> None:
        assert codes(snapshot(active_loans=2)) == []

    def test_three_active_loans_cannot_reserve_a_fourth(self) -> None:
        assert codes(snapshot(active_loans=3)) == ["ACTIVE_LOAN_LIMIT_REACHED"]

    def test_limit_does_not_block_checking_out_an_existing_reservation(self) -> None:
        assert codes(snapshot(active_loans=3), for_new_reservation=False) == []


def test_suspended_member_is_blocked() -> None:
    assert codes(snapshot(status=MemberStatus.SUSPENDED)) == ["MEMBER_SUSPENDED"]


def test_all_reasons_are_reported_together() -> None:
    snap = snapshot(
        status=MemberStatus.SUSPENDED,
        balance_paise=50_000,
        active_loans=3,
        worst_days_overdue=30,
    )
    assert codes(snap) == [
        "MEMBER_SUSPENDED",
        "FEE_BALANCE_OVER_LIMIT",
        "LOAN_OVERDUE_TOO_LONG",
        "ACTIVE_LOAN_LIMIT_REACHED",
    ]
