from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.errors import BusinessRuleViolation, ConflictError, InvalidTransitionError
from app.domain.statuses import MemberStatus
from app.services import loans as loan_service
from app.services import members as member_service
from app.services import payments as payment_service
from tests.conftest import T0


def owe(session: Session, member_id: int, item_id: int, days_late: int) -> None:
    """Borrow an item and bring it back `days_late` days late, charging ₹10/day."""
    loan_id = loan_service.reserve_item(
        session, member_id=member_id, item_id=item_id, now=T0
    ).loan.id
    loan_service.check_out(session, loan_id=loan_id, now=T0)
    loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(days=7 + days_late))


def detail(session: Session, member_id: int, at=T0):  # type: ignore[no-untyped-def]
    return member_service.get_member_detail(session, member_id=member_id, now=at)


class TestBalanceThreshold:
    def test_member_owing_exactly_100_rupees_can_borrow(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        owe(session, member_id, make_item(), days_late=10)
        info = detail(session, member_id, T0 + timedelta(days=20))
        assert info.balance_paise == 10_000
        assert info.eligibility.can_borrow

    def test_member_owing_110_rupees_is_blocked_with_explanation(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        member_id = make_member()
        owe(session, member_id, make_item(), days_late=11)
        info = detail(session, member_id, T0 + timedelta(days=20))
        assert not info.eligibility.can_borrow
        assert [b.code for b in info.eligibility.blocks] == ["FEE_BALANCE_OVER_LIMIT"]
        assert "₹110" in info.eligibility.blocks[0].message


class TestPayments:
    def test_payment_reduces_balance_and_unblocks(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        owe(session, member_id, make_item(), days_late=12)
        later = T0 + timedelta(days=20)
        _, balance = payment_service.record_payment(
            session, member_id=member_id, amount_paise=5_000, note="Cash", now=later
        )
        assert balance == 7_000
        assert detail(session, member_id, later).eligibility.can_borrow

    def test_paying_exact_balance_clears_it(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        owe(session, member_id, make_item(), days_late=3)
        _, balance = payment_service.record_payment(
            session, member_id=member_id, amount_paise=3_000, note="", now=T0 + timedelta(days=11)
        )
        assert balance == 0

    def test_paying_more_than_balance_is_refused(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        owe(session, member_id, make_item(), days_late=3)
        with pytest.raises(BusinessRuleViolation) as error:
            payment_service.record_payment(
                session,
                member_id=member_id,
                amount_paise=3_001,
                note="",
                now=T0 + timedelta(days=11),
            )
        assert error.value.code == "PAYMENT_EXCEEDS_BALANCE"
        assert error.value.details["balance_paise"] == 3_000

    def test_paying_with_nothing_owed_is_refused(self, session: Session, make_member) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(BusinessRuleViolation):
            payment_service.record_payment(
                session, member_id=make_member(), amount_paise=100, note="", now=T0
            )

    def test_statement_adds_up(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        owe(session, member_id, make_item("A"), days_late=4)
        owe(session, member_id, make_item("B"), days_late=2)
        later = T0 + timedelta(days=20)
        payment_service.record_payment(
            session, member_id=member_id, amount_paise=2_500, note="UPI", now=later
        )
        statement = member_service.get_statement(session, member_id=member_id, now=later)
        assert statement.total_fees_charged_paise == 6_000
        assert statement.total_paid_paise == 2_500
        assert statement.balance_paise == 3_500
        assert len(statement.loans) == 2 and len(statement.payments) == 1

    def test_statement_shows_fees_accruing_on_overdue_loans(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        member_id = make_member()
        loan_id = loan_service.reserve_item(
            session, member_id=member_id, item_id=make_item(), now=T0
        ).loan.id
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        statement = member_service.get_statement(
            session, member_id=member_id, now=T0 + timedelta(days=9)
        )
        assert statement.balance_paise == 0
        assert statement.accrued_unbilled_fees_paise == 2_000


class TestSuspension:
    def test_suspended_member_cannot_reserve(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        member_service.suspend_member(session, member_id=member_id, reason="Damage", now=T0)
        with pytest.raises(BusinessRuleViolation) as error:
            loan_service.reserve_item(session, member_id=member_id, item_id=make_item(), now=T0)
        assert error.value.code == "MEMBER_SUSPENDED"

    def test_suspended_member_cannot_collect_existing_reservation(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        member_id = make_member()
        loan_id = loan_service.reserve_item(
            session, member_id=member_id, item_id=make_item(), now=T0
        ).loan.id
        member_service.suspend_member(session, member_id=member_id, reason="Damage", now=T0)
        with pytest.raises(BusinessRuleViolation):
            loan_service.check_out(session, loan_id=loan_id, now=T0)

    def test_suspended_member_can_still_return_and_pay(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        member_id = make_member()
        loan_id = loan_service.reserve_item(
            session, member_id=member_id, item_id=make_item(), now=T0
        ).loan.id
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        member_service.suspend_member(session, member_id=member_id, reason="Damage", now=T0)
        late = T0 + timedelta(days=9)
        loan_service.return_item(session, loan_id=loan_id, now=late)
        _, balance = payment_service.record_payment(
            session, member_id=member_id, amount_paise=2_000, note="", now=late
        )
        assert balance == 0

    def test_suspension_is_reversible_and_keeps_history(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        member_service.suspend_member(session, member_id=member_id, reason="Late again", now=T0)
        reinstated = member_service.reinstate_member(
            session, member_id=member_id, reason="Committee cleared", now=T0 + timedelta(days=1)
        )
        assert reinstated.member.status == MemberStatus.ACTIVE
        assert [(c.from_status, c.to_status, c.reason) for c in reinstated.status_changes] == [
            ("active", "suspended", "Late again"),
            ("suspended", "active", "Committee cleared"),
        ]
        assert loan_service.reserve_item(
            session, member_id=member_id, item_id=make_item(), now=T0 + timedelta(days=1)
        )

    def test_suspending_twice_is_an_error(self, session: Session, make_member) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        member_service.suspend_member(session, member_id=member_id, reason="x", now=T0)
        with pytest.raises(InvalidTransitionError) as error:
            member_service.suspend_member(session, member_id=member_id, reason="x", now=T0)
        assert error.value.code == "ALREADY_SUSPENDED"

    def test_reinstating_an_active_member_is_an_error(self, session: Session, make_member) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(InvalidTransitionError):
            member_service.reinstate_member(session, member_id=make_member(), reason="x", now=T0)


class TestMemberRecords:
    def test_duplicate_phone_is_a_conflict(self, session: Session, make_member) -> None:  # type: ignore[no-untyped-def]
        make_member(phone="+919800000001")
        with pytest.raises(ConflictError):
            member_service.create_member(
                session,
                new_member=member_service.NewMember("Other", "+919800000001", None),
                now=T0,
            )

    def test_join_date_defaults_to_ist_today(self, session: Session) -> None:
        view = member_service.create_member(
            session, new_member=member_service.NewMember("New", "+919800000002", None), now=T0
        )
        assert view.member.joined_on == date(2026, 10, 20)

    def test_future_join_date_is_refused(self, session: Session) -> None:
        with pytest.raises(BusinessRuleViolation):
            member_service.create_member(
                session,
                new_member=member_service.NewMember("New", "+919800000003", date(2026, 10, 21)),
                now=T0,
            )

    def test_member_with_history_cannot_be_deleted(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        loan_service.reserve_item(session, member_id=member_id, item_id=make_item(), now=T0)
        with pytest.raises(ConflictError):
            member_service.delete_member(session, member_id=member_id)

    def test_member_without_history_can_be_deleted(self, session: Session, make_member) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        member_service.suspend_member(session, member_id=member_id, reason="Duplicate", now=T0)
        member_service.delete_member(session, member_id=member_id)
        _, total = member_service.list_members(
            session, search=None, status=None, limit=10, offset=0
        )
        assert total == 0
