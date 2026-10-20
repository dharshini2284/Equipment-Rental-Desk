"""Races and rollbacks: the cases a single-threaded happy-path test cannot catch."""

import threading
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.errors import BusinessRuleViolation, DomainError, InvalidTransitionError
from app.persistence.models import Item, Loan, Notification, Payment
from app.services import loans as loan_service
from app.services import members as member_service
from app.services import payments as payment_service
from tests.conftest import T0


def run_concurrently(tasks: list[Callable[[], object]]) -> list[object]:
    """Start all tasks at the same moment; return each result or the exception it raised."""
    barrier = threading.Barrier(len(tasks))
    results: list[object] = [None] * len(tasks)

    def worker(index: int, task: Callable[[], object]) -> None:
        barrier.wait()
        try:
            results[index] = task()
        except Exception as error:  # collected for assertions below
            results[index] = error

    threads = [threading.Thread(target=worker, args=(i, t)) for i, t in enumerate(tasks)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def in_new_session(session_factory: sessionmaker[Session], action):  # type: ignore[no-untyped-def]
    def task() -> object:
        with session_factory() as session:
            return action(session)

    return task


def test_two_simultaneous_checkouts_only_one_wins(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    with session_factory() as session:
        loan_id = loan_service.reserve_item(
            session, member_id=make_member(), item_id=make_item(), now=T0
        ).loan.id

    checkout = in_new_session(
        session_factory, lambda s: loan_service.check_out(s, loan_id=loan_id, now=T0)
    )
    results = run_concurrently([checkout, checkout, checkout])

    errors = [r for r in results if isinstance(r, Exception)]
    assert len(results) - len(errors) == 1
    assert all(isinstance(e, InvalidTransitionError) for e in errors), errors


def test_two_members_reserving_the_same_item_only_one_wins(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    item_id = make_item()
    members = [make_member(f"Member {n}") for n in range(4)]
    tasks = [
        in_new_session(
            session_factory,
            lambda s, m=m: loan_service.reserve_item(s, member_id=m, item_id=item_id, now=T0),
        )
        for m in members
    ]
    results = run_concurrently(tasks)

    assert sum(not isinstance(r, Exception) for r in results) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count(Loan.id))) == 1


def test_parallel_reservations_cannot_exceed_the_loan_limit(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    member_id = make_member()
    items = [make_item(f"Tool {n}") for n in range(6)]
    tasks = [
        in_new_session(
            session_factory,
            lambda s, i=i: loan_service.reserve_item(s, member_id=member_id, item_id=i, now=T0),
        )
        for i in items
    ]
    results = run_concurrently(tasks)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 3
    assert all(
        isinstance(f, BusinessRuleViolation) and f.code == "ACTIVE_LOAN_LIMIT_REACHED"
        for f in failures
    )


def test_parallel_payments_cannot_overpay(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    member_id = make_member()
    with session_factory() as session:
        loan_id = loan_service.reserve_item(
            session, member_id=member_id, item_id=make_item(), now=T0
        ).loan.id
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        loan_service.return_item(session, loan_id=loan_id, now=T0 + timedelta(days=12))  # ₹50

    pay_30 = in_new_session(
        session_factory,
        lambda s: payment_service.record_payment(
            s, member_id=member_id, amount_paise=3_000, note="", now=T0 + timedelta(days=12)
        ),
    )
    results = run_concurrently([pay_30, pay_30])

    assert sum(isinstance(r, BusinessRuleViolation) for r in results) == 1
    with session_factory() as session:
        assert session.scalar(select(func.sum(Payment.amount_paise))) == 3_000


def test_refused_reservation_leaves_no_partial_writes(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    """A refused reservation writes no loan and no message.

    Closing the lapsed hold it found *is* kept: that is committed on purpose, before the
    request is judged, so the waitlist's turn survives a refused walk-up (see
    services/waitlist.hand_lapsed_hold_to_queue). It only records what reads already show.
    """
    item_id = make_item()
    first = make_member("First")
    blocked = make_member("Blocked")
    with session_factory() as session:
        old_loan = loan_service.reserve_item(
            session, member_id=first, item_id=item_id, now=T0
        ).loan.id
        member_service.suspend_member(session, member_id=blocked, reason="test", now=T0)
        messages_before = session.scalar(select(func.count(Notification.id)))
        session.rollback()

    with session_factory() as session, pytest.raises(BusinessRuleViolation):
        loan_service.reserve_item(
            session, member_id=blocked, item_id=item_id, now=T0 + timedelta(hours=49)
        )

    with session_factory() as session:
        assert session.scalar(select(func.count(Loan.id))) == 1
        assert session.scalar(select(func.count(Notification.id))) == messages_before
        assert session.get(Loan, old_loan).status == "expired"  # type: ignore[union-attr]
        assert session.get(Item, item_id).status == "available"  # type: ignore[union-attr]


def test_database_constraint_backs_up_the_service_check(
    session_factory: sessionmaker[Session],
    make_member,
    make_item,  # type: ignore[no-untyped-def]
) -> None:
    """Even if code bypassed the service, the partial unique index refuses a second open loan."""
    member_id, item_id = make_member(), make_item()
    with session_factory() as session:
        loan_service.reserve_item(session, member_id=member_id, item_id=item_id, now=T0)
    with session_factory() as session, pytest.raises(IntegrityError), session.begin():
        session.add(Loan(member_id=member_id, item_id=item_id, status="reserved", reserved_at=T0))


def test_domain_errors_are_not_integrity_errors() -> None:
    # Guard against someone making DomainError inherit from a DB error by accident.
    assert not issubclass(DomainError, IntegrityError)
