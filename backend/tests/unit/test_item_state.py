from datetime import UTC, datetime, timedelta

import pytest

from app.domain.errors import InvalidTransitionError
from app.domain.item_state import (
    ALLOWED_ACTIONS,
    effective_item_status,
    effective_loan_status,
    ensure_action_allowed,
    ensure_loan_action_allowed,
)
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus

NOW = datetime(2026, 10, 20, 4, 30, tzinfo=UTC)


class TestEffectiveItemStatus:
    def test_available_stays_available(self) -> None:
        assert effective_item_status(ItemStatus.AVAILABLE, None, None, NOW) == ItemStatus.AVAILABLE

    def test_fresh_reservation_is_reserved(self) -> None:
        reserved_at = NOW - timedelta(hours=47, minutes=59)
        assert (
            effective_item_status(ItemStatus.RESERVED, reserved_at, None, NOW)
            == ItemStatus.RESERVED
        )

    def test_lapsed_reservation_reads_as_available(self) -> None:
        reserved_at = NOW - timedelta(hours=48, minutes=1)
        assert (
            effective_item_status(ItemStatus.RESERVED, reserved_at, None, NOW)
            == ItemStatus.AVAILABLE
        )

    def test_checked_out_before_due(self) -> None:
        due_at = NOW + timedelta(days=1)
        status = effective_item_status(ItemStatus.CHECKED_OUT, NOW, due_at, NOW)
        assert status == ItemStatus.CHECKED_OUT

    def test_checked_out_at_exact_due_time_is_not_overdue(self) -> None:
        assert (
            effective_item_status(ItemStatus.CHECKED_OUT, NOW, NOW, NOW) == ItemStatus.CHECKED_OUT
        )

    def test_checked_out_past_due_reads_as_overdue(self) -> None:
        due_at = NOW - timedelta(seconds=1)
        assert effective_item_status(ItemStatus.CHECKED_OUT, NOW, due_at, NOW) == ItemStatus.OVERDUE

    def test_maintenance_is_unaffected_by_clock(self) -> None:
        status = effective_item_status(ItemStatus.MAINTENANCE, None, None, NOW)
        assert status == ItemStatus.MAINTENANCE


class TestEffectiveLoanStatus:
    def test_reserved_lapses_to_expired(self) -> None:
        reserved_at = NOW - timedelta(hours=48)
        assert (
            effective_loan_status(LoanStatus.RESERVED, reserved_at, None, NOW) == LoanStatus.EXPIRED
        )

    def test_checked_out_becomes_overdue(self) -> None:
        status = effective_loan_status(
            LoanStatus.CHECKED_OUT, NOW - timedelta(days=8), NOW - timedelta(days=1), NOW
        )
        assert status == LoanStatus.OVERDUE

    def test_returned_is_final(self) -> None:
        status = effective_loan_status(
            LoanStatus.RETURNED, NOW - timedelta(days=30), NOW - timedelta(days=20), NOW
        )
        assert status == LoanStatus.RETURNED


VALID_TRANSITIONS = [
    (ItemStatus.AVAILABLE, ItemAction.RESERVE),
    (ItemStatus.AVAILABLE, ItemAction.SEND_TO_MAINTENANCE),
    (ItemStatus.RESERVED, ItemAction.CHECK_OUT),
    (ItemStatus.RESERVED, ItemAction.CANCEL_RESERVATION),
    (ItemStatus.RESERVED, ItemAction.SEND_TO_MAINTENANCE),
    (ItemStatus.CHECKED_OUT, ItemAction.RETURN),
    (ItemStatus.OVERDUE, ItemAction.RETURN),
    (ItemStatus.MAINTENANCE, ItemAction.RETURN_TO_SERVICE),
    # Anything not available can be queued for.
    (ItemStatus.RESERVED, ItemAction.JOIN_WAITLIST),
    (ItemStatus.CHECKED_OUT, ItemAction.JOIN_WAITLIST),
    (ItemStatus.OVERDUE, ItemAction.JOIN_WAITLIST),
    (ItemStatus.MAINTENANCE, ItemAction.JOIN_WAITLIST),
]


@pytest.mark.parametrize(("status", "action"), VALID_TRANSITIONS)
def test_valid_transitions_are_allowed(status: ItemStatus, action: ItemAction) -> None:
    ensure_action_allowed(status, action, item_id=1)


INVALID_TRANSITIONS = [
    (status, action)
    for status in ItemStatus
    for action in ItemAction
    if (status, action) not in VALID_TRANSITIONS
]


@pytest.mark.parametrize(("status", "action"), INVALID_TRANSITIONS)
def test_every_other_transition_is_rejected(status: ItemStatus, action: ItemAction) -> None:
    with pytest.raises(InvalidTransitionError) as error:
        ensure_action_allowed(status, action, item_id=7)
    assert error.value.details["item_id"] == 7
    assert error.value.details["current_status"] == status.value


def test_checked_out_item_cannot_go_straight_to_maintenance_and_says_why() -> None:
    with pytest.raises(InvalidTransitionError, match="Record the return first"):
        ensure_action_allowed(ItemStatus.CHECKED_OUT, ItemAction.SEND_TO_MAINTENANCE, item_id=1)


def test_every_status_has_an_action_list() -> None:
    assert set(ALLOWED_ACTIONS) == set(ItemStatus)


class TestLoanActions:
    def test_returned_loan_cannot_be_returned_again(self) -> None:
        with pytest.raises(InvalidTransitionError) as error:
            ensure_loan_action_allowed(5, LoanStatus.RETURNED, ItemAction.RETURN)
        assert error.value.code == "INVALID_TRANSITION"

    def test_expired_reservation_has_its_own_code(self) -> None:
        with pytest.raises(InvalidTransitionError) as error:
            ensure_loan_action_allowed(5, LoanStatus.EXPIRED, ItemAction.CHECK_OUT)
        assert error.value.code == "RESERVATION_EXPIRED"

    def test_reserved_loan_cannot_be_returned(self) -> None:
        with pytest.raises(InvalidTransitionError):
            ensure_loan_action_allowed(5, LoanStatus.RESERVED, ItemAction.RETURN)

    def test_overdue_loan_can_be_returned(self) -> None:
        ensure_loan_action_allowed(5, LoanStatus.OVERDUE, ItemAction.RETURN)
