"""Reservation expiry (read time and write time) and the 3-active-loan limit."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import BusinessRuleViolation, InvalidTransitionError
from app.domain.statuses import ItemStatus, LoanStatus
from app.persistence.models import Loan
from app.services import items as item_service
from app.services import loans as loan_service
from tests.conftest import T0


def reserve(session: Session, member_id: int, item_id: int, at=T0) -> int:  # type: ignore[no-untyped-def]
    return loan_service.reserve_item(session, member_id=member_id, item_id=item_id, now=at).loan.id


class TestExpiry:
    def test_checkout_at_47h59m_succeeds(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        view = loan_service.check_out(
            session, loan_id=loan_id, now=T0 + timedelta(hours=47, minutes=59)
        )
        assert view.status == LoanStatus.CHECKED_OUT

    def test_checkout_at_48h01m_fails_as_expired(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        with pytest.raises(InvalidTransitionError) as error:
            loan_service.check_out(
                session, loan_id=loan_id, now=T0 + timedelta(hours=48, minutes=1)
            )
        assert error.value.code == "RESERVATION_EXPIRED"

    def test_lapsed_reservation_reads_as_available_without_writing(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        item_id = make_item()
        loan_id = reserve(session, make_member(), item_id)
        later = T0 + timedelta(hours=48, minutes=1)

        detail = item_service.get_item(session, item_id=item_id, now=later)
        assert detail.status == ItemStatus.AVAILABLE
        assert detail.current_loan is None
        # Reading did not change the stored row.
        with session.begin():
            assert session.get(Loan, loan_id).status == LoanStatus.RESERVED  # type: ignore[union-attr]

    def test_lapsed_reservation_appears_under_available_filter(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        item_id = make_item()
        reserve(session, make_member(), item_id)
        later = T0 + timedelta(hours=48)
        views, total = item_service.list_items(
            session,
            now=later,
            status=ItemStatus.AVAILABLE,
            search=None,
            category=None,
            limit=10,
            offset=0,
        )
        assert total == 1 and views[0].item.id == item_id
        _, reserved_total = item_service.list_items(
            session,
            now=later,
            status=ItemStatus.RESERVED,
            search=None,
            category=None,
            limit=10,
            offset=0,
        )
        assert reserved_total == 0

    def test_another_member_can_reserve_after_expiry_and_old_hold_is_closed(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        item_id = make_item()
        old_loan = reserve(session, make_member("First"), item_id)
        later = T0 + timedelta(hours=48, minutes=1)

        new_loan = reserve(session, make_member("Second"), item_id, at=later)

        with session.begin():
            statuses = dict(session.execute(select(Loan.id, Loan.status)).all())
        assert statuses == {old_loan: LoanStatus.EXPIRED, new_loan: LoanStatus.RESERVED}

    def test_cannot_reserve_an_item_that_is_still_held(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        item_id = make_item()
        reserve(session, make_member("First"), item_id)
        with pytest.raises(InvalidTransitionError):
            reserve(
                session, make_member("Second"), item_id, at=T0 + timedelta(hours=47, minutes=59)
            )

    def test_cancel_after_expiry_reports_expired(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        loan_id = reserve(session, make_member(), make_item())
        with pytest.raises(InvalidTransitionError) as error:
            loan_service.cancel_reservation(session, loan_id=loan_id, now=T0 + timedelta(hours=49))
        assert error.value.code == "RESERVATION_EXPIRED"


class TestActiveLoanLimit:
    def test_fourth_reservation_is_refused(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        items = [make_item(f"Tool {n}") for n in range(4)]
        first = reserve(session, member_id, items[0])
        loan_service.check_out(session, loan_id=first, now=T0)  # checked out counts
        reserve(session, member_id, items[1])  # reserved counts
        reserve(session, member_id, items[2])

        with pytest.raises(BusinessRuleViolation) as error:
            reserve(session, member_id, items[3])
        assert error.value.code == "ACTIVE_LOAN_LIMIT_REACHED"

    def test_overdue_loans_still_count(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        items = [make_item(f"Tool {n}") for n in range(4)]
        for item_id in items[:3]:
            loan_service.check_out(session, loan_id=reserve(session, member_id, item_id), now=T0)
        # Eight days later all three are overdue (by 1 day, well under the 14-day block).
        with pytest.raises(BusinessRuleViolation) as error:
            reserve(session, member_id, items[3], at=T0 + timedelta(days=8))
        assert error.value.code == "ACTIVE_LOAN_LIMIT_REACHED"

    def test_lapsed_reservations_do_not_count(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        items = [make_item(f"Tool {n}") for n in range(4)]
        for item_id in items[:3]:
            reserve(session, member_id, item_id)
        later = T0 + timedelta(hours=48)
        assert reserve(session, member_id, items[3], at=later)

    def test_returned_loans_free_a_slot(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        items = [make_item(f"Tool {n}") for n in range(4)]
        loans = [reserve(session, member_id, item_id) for item_id in items[:3]]
        loan_service.check_out(session, loan_id=loans[0], now=T0)
        loan_service.return_item(session, loan_id=loans[0], now=T0 + timedelta(hours=3))
        assert reserve(session, member_id, items[3], at=T0 + timedelta(hours=3))


class TestOverdueBlock:
    def _member_with_loan_due(self, session: Session, make_member, make_item) -> int:  # type: ignore[no-untyped-def]
        member_id = make_member()
        loan_service.check_out(
            session, loan_id=reserve(session, member_id, make_item("Out")), now=T0
        )
        return member_id

    def test_overdue_exactly_14_days_can_still_reserve(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        member_id = self._member_with_loan_due(session, make_member, make_item)
        at = T0 + timedelta(days=7 + 14)
        assert reserve(session, member_id, make_item("Next"), at=at)

    def test_overdue_more_than_14_days_blocks(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = self._member_with_loan_due(session, make_member, make_item)
        at = T0 + timedelta(days=7 + 14, seconds=1)
        with pytest.raises(BusinessRuleViolation) as error:
            reserve(session, member_id, make_item("Next"), at=at)
        assert error.value.code == "LOAN_OVERDUE_TOO_LONG"
