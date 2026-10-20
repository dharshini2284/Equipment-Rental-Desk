"""Reserve -> check out -> return, against a real SQLite database."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import BusinessRuleViolation, InvalidTransitionError, NotFoundError
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus
from app.persistence import queries
from app.services import items as item_service
from app.services import loans as loan_service
from tests.conftest import T0


def reserve(session: Session, member_id: int, item_id: int, at=T0) -> int:  # type: ignore[no-untyped-def]
    return loan_service.reserve_item(session, member_id=member_id, item_id=item_id, now=at).loan.id


def item_status(session: Session, item_id: int, at=T0) -> ItemStatus:  # type: ignore[no-untyped-def]
    return item_service.get_item(session, item_id=item_id, now=at).status


def test_full_happy_path(session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
    member_id, item_id = make_member(), make_item()

    loan_id = reserve(session, member_id, item_id)
    assert item_status(session, item_id) == ItemStatus.RESERVED

    checkout_at = T0 + timedelta(hours=2)
    view = loan_service.check_out(session, loan_id=loan_id, now=checkout_at)
    assert view.status == LoanStatus.CHECKED_OUT
    assert view.loan.due_at == checkout_at + timedelta(days=7)
    assert item_status(session, item_id, checkout_at) == ItemStatus.CHECKED_OUT

    returned = loan_service.return_item(
        session, loan_id=loan_id, now=checkout_at + timedelta(days=5)
    )
    assert returned.status == LoanStatus.RETURNED
    assert returned.loan.fee_charged_paise == 0
    assert item_status(session, item_id, checkout_at + timedelta(days=5)) == ItemStatus.AVAILABLE


def test_item_detail_lists_only_valid_actions(session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
    member_id, item_id = make_member(), make_item()
    detail = item_service.get_item(session, item_id=item_id, now=T0)
    assert detail.allowed_actions == (ItemAction.RESERVE, ItemAction.SEND_TO_MAINTENANCE)

    loan_id = reserve(session, member_id, item_id)
    loan_service.check_out(session, loan_id=loan_id, now=T0)
    detail = item_service.get_item(session, item_id=item_id, now=T0)
    assert detail.allowed_actions == (ItemAction.RETURN, ItemAction.JOIN_WAITLIST)
    assert detail.current_loan is not None and detail.current_loan.loan.id == loan_id


def test_overdue_is_derived_from_the_clock(session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
    member_id, item_id = make_member(), make_item()
    loan_id = reserve(session, member_id, item_id)
    loan_service.check_out(session, loan_id=loan_id, now=T0)

    due = T0 + timedelta(days=7)
    assert item_status(session, item_id, due) == ItemStatus.CHECKED_OUT
    assert item_status(session, item_id, due + timedelta(seconds=1)) == ItemStatus.OVERDUE

    overdue, total = loan_service.list_overdue_loans(
        session, now=due + timedelta(days=3), limit=10, offset=0
    )
    assert total == 1
    assert overdue[0].days_overdue == 3
    assert overdue[0].accrued_fee_paise == 3_000


class TestReturn:
    def test_late_return_charges_fee_to_member(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id, item_id = make_member(), make_item()
        loan_id = reserve(session, member_id, item_id)
        loan_service.check_out(session, loan_id=loan_id, now=T0)

        returned_at = T0 + timedelta(days=7, hours=50)  # 2 days 2 hours late -> 3 days
        view = loan_service.return_item(session, loan_id=loan_id, now=returned_at)

        assert view.loan.fee_charged_paise == 3_000
        with session.begin():
            assert queries.member_balance_paise(session, member_id) == 3_000

    def test_fee_capped_at_replacement_value(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        item_id = make_item("Stud finder", replacement_value_paise=15_000)
        loan_id = reserve(session, member_id, item_id)
        loan_service.check_out(session, loan_id=loan_id, now=T0)

        view = loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(days=7 + 19))
        assert view.loan.fee_charged_paise == 15_000

    def test_returning_twice_is_an_error(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id, item_id = make_member(), make_item()
        loan_id = reserve(session, member_id, item_id)
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        late = T0 + timedelta(days=9)
        loan_service.return_item(session, loan_id=loan_id, now=late)

        with pytest.raises(InvalidTransitionError):
            loan_service.return_item(session, loan_id=loan_id, now=late)
        # The fee was charged once, not twice.
        with session.begin():
            assert queries.member_balance_paise(session, member_id) == 2_000

    def test_returning_a_reserved_item_is_an_error(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        with pytest.raises(InvalidTransitionError, match="reserved"):
            loan_service.return_item(session, loan_id=loan_id, now=T0)

    def test_return_can_send_item_to_maintenance(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id, item_id = make_member(), make_item()
        loan_id = reserve(session, member_id, item_id)
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        loan_service.return_item(
            session,
            loan_id=loan_id,
            now=T0 + timedelta(days=1),
            send_to_maintenance=True,
            condition_note="Chuck is loose",
        )
        detail = item_service.get_item(session, item_id=item_id, now=T0 + timedelta(days=1))
        assert detail.status == ItemStatus.MAINTENANCE
        assert detail.item.condition_note == "Chuck is loose"

    def test_cannot_return_before_checkout_time(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        loan_service.check_out(session, loan_id=loan_id, now=T0 + timedelta(days=1))
        with pytest.raises(InvalidTransitionError) as error:
            loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(hours=12))
        assert error.value.code == "CLOCK_BEFORE_PREVIOUS_EVENT"


class TestCheckout:
    def test_double_checkout_is_rejected(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        with pytest.raises(InvalidTransitionError, match="checked out"):
            loan_service.check_out(session, loan_id=loan_id, now=T0 + timedelta(seconds=2))

    def test_checkout_rechecks_member_eligibility(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        """A member who ran up fees after reserving cannot collect the reservation."""
        member_id = make_member()
        first_item, second_item = make_item("Ladder"), make_item("Tiller")
        first = reserve(session, member_id, first_item)
        loan_service.check_out(session, loan_id=first, now=T0)
        later = T0 + timedelta(days=7 + 12)
        second = reserve(session, member_id, second_item, at=later)
        loan_service.return_item(session, loan_id=first, now=later)  # ₹120 fee

        with pytest.raises(BusinessRuleViolation) as error:
            loan_service.check_out(session, loan_id=second, now=later)
        assert error.value.code == "FEE_BALANCE_OVER_LIMIT"

    def test_unknown_loan(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            loan_service.check_out(session, loan_id=999, now=T0)


class TestCancel:
    def test_cancel_frees_the_item(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        loan_id = reserve(session, make_member(), item_id)
        view = loan_service.cancel_reservation(
            session, loan_id=loan_id, now=T0 + timedelta(hours=1)
        )
        assert view.status == LoanStatus.CANCELLED
        assert item_status(session, item_id) == ItemStatus.AVAILABLE

    def test_cannot_cancel_a_checked_out_loan(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        with pytest.raises(InvalidTransitionError):
            loan_service.cancel_reservation(session, loan_id=loan_id, now=T0)


def test_loan_history_lists_newest_first(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    member_id, item_id = make_member(), make_item()
    with session_factory() as session:
        first = reserve(session, member_id, item_id)
        loan_service.cancel_reservation(session, loan_id=first, now=T0)
        second = reserve(session, member_id, item_id, at=T0 + timedelta(hours=1))
        loans, total = loan_service.list_loans(
            session, now=T0, member_id=member_id, item_id=None, limit=10, offset=0
        )
    assert total == 2
    assert [view.loan.id for view in loans] == [second, first]
