from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.errors import ConflictError, InvalidTransitionError
from app.domain.statuses import ItemStatus, LoanStatus
from app.services import items as item_service
from app.services import loans as loan_service
from tests.conftest import T0


def list_ids(session: Session, at=T0, **filters) -> list[int]:  # type: ignore[no-untyped-def]
    params = {"status": None, "search": None, "category": None, "limit": 50, "offset": 0}
    params.update(filters)
    views, _ = item_service.list_items(session, now=at, **params)
    return [view.item.id for view in views]


class TestMaintenance:
    def test_available_item_round_trip(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        view = item_service.send_to_maintenance(
            session, item_id=item_id, now=T0, condition_note="Brushes worn"
        )
        assert view.status == ItemStatus.MAINTENANCE
        view = item_service.return_to_service(session, item_id=item_id, now=T0, condition_note=None)
        assert view.status == ItemStatus.AVAILABLE
        assert view.item.condition_note == "Brushes worn"

    def test_reserved_item_to_maintenance_cancels_reservation(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        item_id = make_item()
        loan_id = loan_service.reserve_item(
            session, member_id=make_member(), item_id=item_id, now=T0
        ).loan.id
        item_service.send_to_maintenance(session, item_id=item_id, now=T0, condition_note=None)
        assert (
            loan_service.get_loan(session, loan_id=loan_id, now=T0).status == LoanStatus.CANCELLED
        )

    def test_checked_out_item_cannot_go_to_maintenance(
        self,
        session: Session,
        make_member,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        item_id = make_item()
        loan_id = loan_service.reserve_item(
            session, member_id=make_member(), item_id=item_id, now=T0
        ).loan.id
        loan_service.check_out(session, loan_id=loan_id, now=T0)
        with pytest.raises(InvalidTransitionError):
            item_service.send_to_maintenance(session, item_id=item_id, now=T0, condition_note=None)

    def test_item_in_maintenance_cannot_be_reserved(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        item_service.send_to_maintenance(session, item_id=item_id, now=T0, condition_note=None)
        with pytest.raises(InvalidTransitionError):
            loan_service.reserve_item(session, member_id=make_member(), item_id=item_id, now=T0)

    def test_return_to_service_only_from_maintenance(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(InvalidTransitionError):
            item_service.return_to_service(
                session, item_id=make_item(), now=T0, condition_note=None
            )

    def test_maintenance_twice_is_an_error(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        item_service.send_to_maintenance(session, item_id=item_id, now=T0, condition_note=None)
        with pytest.raises(InvalidTransitionError):
            item_service.send_to_maintenance(session, item_id=item_id, now=T0, condition_note=None)


class TestListing:
    def test_filters_by_live_status(self, session: Session, make_member, make_item) -> None:  # type: ignore[no-untyped-def]
        member_id = make_member()
        free, held, out, late = (make_item(n) for n in ("Free", "Held", "Out", "Late"))
        loan_service.check_out(
            session,
            loan_id=loan_service.reserve_item(
                session, member_id=member_id, item_id=late, now=T0 - timedelta(days=10)
            ).loan.id,
            now=T0 - timedelta(days=10),
        )
        loan_service.check_out(
            session,
            loan_id=loan_service.reserve_item(
                session, member_id=member_id, item_id=out, now=T0
            ).loan.id,
            now=T0,
        )
        loan_service.reserve_item(session, member_id=member_id, item_id=held, now=T0)

        assert list_ids(session, status=ItemStatus.AVAILABLE) == [free]
        assert list_ids(session, status=ItemStatus.RESERVED) == [held]
        assert list_ids(session, status=ItemStatus.CHECKED_OUT) == [out]
        assert list_ids(session, status=ItemStatus.OVERDUE) == [late]

    def test_search_matches_name_and_category_case_insensitively(
        self,
        session: Session,
        make_item,  # type: ignore[no-untyped-def]
    ) -> None:
        drill = make_item("Cordless DRILL")
        make_item("Ladder")
        assert list_ids(session, search="drill") == [drill]
        assert len(list_ids(session, search="power")) == 2  # category "Power tools"

    def test_search_treats_wildcards_literally(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        make_item("Ladder")
        assert list_ids(session, search="%") == []
        assert list_ids(session, search="_") == []

    def test_pagination(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        ids = [make_item(f"Tool {n}") for n in range(5)]
        views, total = item_service.list_items(
            session, now=T0, status=None, search=None, category=None, limit=2, offset=2
        )
        assert total == 5
        assert [v.item.id for v in views] == ids[2:4]


class TestEditing:
    def test_update_changes_fields(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        view = item_service.update_item(
            session, item_id=item_id, changes={"replacement_value_paise": 9_900}, now=T0
        )
        assert view.item.replacement_value_paise == 9_900

    def test_item_with_loans_cannot_be_deleted(
        self, session: Session, make_member, make_item
    ) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        loan_service.reserve_item(session, member_id=make_member(), item_id=item_id, now=T0)
        with pytest.raises(ConflictError):
            item_service.delete_item(session, item_id=item_id)

    def test_unused_item_can_be_deleted(self, session: Session, make_item) -> None:  # type: ignore[no-untyped-def]
        item_id = make_item()
        item_service.delete_item(session, item_id=item_id)
        assert list_ids(session) == []
