"""Waitlist promotion and the notification outbox, against a real database."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import BusinessRuleViolation, ConflictError, InvalidTransitionError
from app.domain.statuses import ItemStatus, LoanStatus, WaitlistStatus
from app.persistence.models import Loan, Notification
from app.services import items as item_service
from app.services import loans as loan_service
from app.services import members as member_service
from app.services import notifications as notification_service
from app.services import payments as payment_service
from app.services import waitlist as waitlist_service
from tests.conftest import T0
from tests.integration.test_concurrency_and_transactions import in_new_session, run_concurrently


def lend(session: Session, member_id: int, item_id: int, at=T0) -> int:
    loan_id = loan_service.reserve_item(
        session, member_id=member_id, item_id=item_id, now=at
    ).loan.id
    loan_service.check_out(session, loan_id=loan_id, now=at)
    return loan_id


def join(session: Session, member_id: int, item_id: int, at=T0):
    return waitlist_service.join_waitlist(session, member_id=member_id, item_id=item_id, now=at)


def queue(session: Session, item_id: int) -> list[tuple[int, int | None]]:
    views, _ = waitlist_service.list_waitlist(
        session, item_id=item_id, member_id=None, status=WaitlistStatus.WAITING, limit=50, offset=0
    )
    return [(view.entry.member_id, view.position) for view in views]


def kinds_for(session: Session, member_id: int) -> list[str]:
    rows, _ = notification_service.list_notifications(
        session, member_id=member_id, kind=None, limit=100, offset=0
    )
    return [row.kind for row in reversed(rows)]  # oldest first


class TestJoining:
    def test_queue_positions_follow_join_order(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id = make_item()
        lend(session, make_member("Holder"), item_id)
        first, second = make_member("First"), make_member("Second")
        assert join(session, first, item_id).position == 1
        assert join(session, second, item_id, T0 + timedelta(minutes=1)).position == 2
        assert queue(session, item_id) == [(first, 1), (second, 2)]

    def test_cannot_queue_for_an_available_item(
        self, session: Session, make_member, make_item
    ) -> None:
        with pytest.raises(InvalidTransitionError):
            join(session, make_member(), make_item())

    def test_cannot_queue_twice_or_for_own_loan(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id, holder, waiter = make_item(), make_member("Holder"), make_member("Waiter")
        lend(session, holder, item_id)
        join(session, waiter, item_id)
        with pytest.raises(ConflictError, match="already on"):
            join(session, waiter, item_id)
        with pytest.raises(ConflictError, match="already has the item"):
            join(session, holder, item_id)

    def test_blocked_member_cannot_queue(self, session: Session, make_member, make_item) -> None:
        item_id, waiter = make_item(), make_member("Waiter")
        lend(session, make_member("Holder"), item_id)
        member_service.suspend_member(session, member_id=waiter, reason="x", now=T0)
        with pytest.raises(BusinessRuleViolation) as error:
            join(session, waiter, item_id)
        assert error.value.code == "MEMBER_SUSPENDED"

    def test_member_at_loan_limit_may_still_queue(
        self, session: Session, make_member, make_item
    ) -> None:
        """The limit is checked when their turn comes; they may have returned something by then."""
        waiter, item_id = make_member("Waiter"), make_item("Wanted")
        for n in range(3):
            lend(session, waiter, make_item(f"Tool {n}"))
        lend(session, make_member("Holder"), item_id)
        assert join(session, waiter, item_id).position == 1

    def test_leaving_the_queue(self, session: Session, make_member, make_item) -> None:
        item_id = make_item()
        lend(session, make_member("Holder"), item_id)
        entry = join(session, make_member("Waiter"), item_id).entry
        left = waitlist_service.leave_waitlist(session, entry_id=entry.id, now=T0)
        assert left.entry.status == WaitlistStatus.CANCELLED and left.position is None
        with pytest.raises(InvalidTransitionError):
            waitlist_service.leave_waitlist(session, entry_id=entry.id, now=T0)


class TestPromotion:
    def test_return_reserves_item_for_first_in_line(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id = make_item()
        loan_id = lend(session, make_member("Holder"), item_id)
        first, second = make_member("First"), make_member("Second")
        join(session, first, item_id)
        join(session, second, item_id, T0 + timedelta(minutes=1))

        returned_at = T0 + timedelta(days=2)
        loan_service.return_item(session, loan_id=loan_id, now=returned_at)

        detail = item_service.get_item(session, item_id=item_id, now=returned_at)
        assert detail.status == ItemStatus.RESERVED
        assert detail.current_loan is not None and detail.current_loan.loan.member_id == first
        assert detail.current_loan.loan.reserved_at == returned_at  # the 48 h starts now
        assert queue(session, item_id) == [(second, 1)]
        assert "waitlist_joined" in kinds_for(session, first)
        assert kinds_for(session, first)[-1] == "waitlist_reserved"

    def test_ineligible_member_is_skipped_with_reason(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id = make_item()
        loan_id = lend(session, make_member("Holder"), item_id)
        skipped, next_up = make_member("Skipped"), make_member("Next")
        join(session, skipped, item_id)
        join(session, next_up, item_id, T0 + timedelta(minutes=1))
        member_service.suspend_member(session, member_id=skipped, reason="x", now=T0)

        loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(days=1))

        views, _ = waitlist_service.list_waitlist(
            session, item_id=item_id, member_id=skipped, status=None, limit=5, offset=0
        )
        assert views[0].entry.status == WaitlistStatus.SKIPPED
        assert "suspended" in views[0].entry.note
        assert kinds_for(session, skipped)[-1] == "waitlist_skipped"
        holder = item_service.get_item(session, item_id=item_id, now=T0 + timedelta(days=1))
        assert holder.current_loan is not None and holder.current_loan.loan.member_id == next_up

    def test_member_at_loan_limit_is_skipped(
        self, session: Session, make_member, make_item
    ) -> None:
        waiter, item_id = make_member("Waiter"), make_item("Wanted")
        loan_id = lend(session, make_member("Holder"), item_id)
        join(session, waiter, item_id)
        for n in range(3):
            lend(session, waiter, make_item(f"Tool {n}"))
        loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(hours=1))
        detail = item_service.get_item(session, item_id=item_id, now=T0 + timedelta(hours=1))
        assert detail.status == ItemStatus.AVAILABLE  # nobody else waiting

    def test_return_to_maintenance_does_not_promote_until_back_in_service(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id, waiter = make_item(), make_member("Waiter")
        loan_id = lend(session, make_member("Holder"), item_id)
        join(session, waiter, item_id)
        loan_service.return_item(session, loan_id=loan_id, now=T0, send_to_maintenance=True)
        assert queue(session, item_id) == [(waiter, 1)]

        view = item_service.return_to_service(session, item_id=item_id, now=T0, condition_note=None)
        assert view.status == ItemStatus.RESERVED
        assert view.current_loan is not None and view.current_loan.loan.member_id == waiter

    def test_cancelling_a_reservation_promotes(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id, waiter = make_item(), make_member("Waiter")
        loan_id = loan_service.reserve_item(
            session, member_id=make_member("Holder"), item_id=item_id, now=T0
        ).loan.id
        join(session, waiter, item_id)
        loan_service.cancel_reservation(session, loan_id=loan_id, now=T0 + timedelta(hours=1))
        assert queue(session, item_id) == []
        assert kinds_for(session, waiter)[-1] == "waitlist_reserved"

    def test_lapsed_hold_goes_to_queue_before_walk_up(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id, waiter, walk_up = make_item(), make_member("Waiter"), make_member("Walk-up")
        loan_service.reserve_item(session, member_id=make_member("Holder"), item_id=item_id, now=T0)
        join(session, waiter, item_id)

        later = T0 + timedelta(hours=49)
        with pytest.raises(InvalidTransitionError):
            loan_service.reserve_item(session, member_id=walk_up, item_id=item_id, now=later)
        detail = item_service.get_item(session, item_id=item_id, now=later)
        assert detail.current_loan is not None and detail.current_loan.loan.member_id == waiter

    def test_first_in_line_reserving_directly_gets_their_hold(
        self, session: Session, make_member, make_item
    ) -> None:
        item_id, waiter = make_item(), make_member("Waiter")
        loan_service.reserve_item(session, member_id=make_member("Holder"), item_id=item_id, now=T0)
        join(session, waiter, item_id)
        view = loan_service.reserve_item(
            session, member_id=waiter, item_id=item_id, now=T0 + timedelta(hours=49)
        )
        assert view.loan.member_id == waiter and view.status == LoanStatus.RESERVED


class TestOutbox:
    def test_lifecycle_messages(self, session: Session, make_member, make_item) -> None:
        member_id = make_member()
        loan_id = lend(session, member_id, make_item("Ladder"))
        loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(days=9))
        assert kinds_for(session, member_id) == ["reservation_created", "checked_out", "returned"]
        rows, _ = notification_service.list_notifications(
            session, member_id=member_id, kind="returned", limit=1, offset=0
        )
        assert "₹20" in rows[0].message and rows[0].recipient.startswith("+91")

    def test_refused_action_leaves_no_message(
        self, session_factory: sessionmaker[Session], make_member, make_item
    ) -> None:
        member_id = make_member()
        with session_factory() as session:
            member_service.suspend_member(session, member_id=member_id, reason="x", now=T0)
            with pytest.raises(BusinessRuleViolation):
                loan_service.reserve_item(session, member_id=member_id, item_id=make_item(), now=T0)
        with session_factory() as session:
            assert kinds_for(session, member_id) == ["member_suspended"]

    def test_overdue_reminders_once_per_day(self, session: Session, make_member, make_item) -> None:
        lend(session, make_member("A"), make_item("Drill"))
        lend(session, make_member("B"), make_item("Saw"))
        lend(session, make_member("C"), make_item("Ladder"), T0 + timedelta(days=5))
        late = T0 + timedelta(days=9)

        assert notification_service.send_overdue_reminders(session, now=late) == (2, 0)
        assert notification_service.send_overdue_reminders(session, now=late) == (0, 2)
        assert notification_service.send_overdue_reminders(
            session, now=late + timedelta(hours=25)
        ) == (2, 0)

    def test_payment_and_suspension_messages(
        self, session: Session, make_member, make_item
    ) -> None:
        member_id = make_member()
        loan_id = lend(session, member_id, make_item())
        loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(days=10))
        payment_service.record_payment(
            session, member_id=member_id, amount_paise=1_000, note="", now=T0 + timedelta(days=10)
        )
        later = T0 + timedelta(days=11)
        member_service.suspend_member(session, member_id=member_id, reason="x", now=later)
        member_service.reinstate_member(session, member_id=member_id, reason="y", now=later)
        assert kinds_for(session, member_id)[-3:] == [
            "payment_received",
            "member_suspended",
            "member_reinstated",
        ]


def test_simultaneous_joins_by_one_member_queue_once(
    session_factory: sessionmaker[Session], make_member, make_item
) -> None:
    item_id, waiter = make_item(), make_member("Waiter")
    with session_factory() as session:
        lend(session, make_member("Holder"), item_id)
    task = in_new_session(
        session_factory,
        lambda s: waitlist_service.join_waitlist(s, member_id=waiter, item_id=item_id, now=T0),
    )
    results = run_concurrently([task, task, task])
    assert sum(not isinstance(r, Exception) for r in results) == 1
    with session_factory() as session:
        assert len(queue(session, item_id)) == 1


def test_simultaneous_returns_and_joins_never_double_book(
    session_factory: sessionmaker[Session], make_member, make_item
) -> None:
    item_id = make_item()
    with session_factory() as session:
        loan_id = lend(session, make_member("Holder"), item_id)
        for n in range(3):
            join(session, make_member(f"Waiter {n}"), item_id, T0 + timedelta(minutes=n))
    tasks = [
        in_new_session(
            session_factory,
            lambda s: loan_service.return_item(s, loan_id=loan_id, now=T0 + timedelta(hours=2)),
        )
        for _ in range(3)
    ]
    run_concurrently(tasks)
    with session_factory() as session:
        assert len(queue(session, item_id)) == 2
    with session_factory() as session:
        open_loans = session.scalar(
            select(func.count(Loan.id)).where(
                Loan.item_id == item_id, Loan.status.in_(["reserved", "checked_out"])
            )
        )
        assert open_loans == 1
        assert (
            session.scalar(
                select(func.count(Notification.id)).where(Notification.kind == "returned")
            )
            == 1
        )
