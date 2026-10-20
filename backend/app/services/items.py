"""Item catalogue and the staff-only maintenance transitions."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.errors import ConflictError
from app.domain.item_state import effective_item_status, ensure_action_allowed
from app.domain.statuses import ItemAction, ItemStatus, LoanStatus
from app.persistence import queries
from app.persistence.models import Item
from app.services.holds import settle_lapsed_reservation
from app.services.notifications import Kind, notify
from app.services.views import ItemView, build_item_view
from app.services.waitlist import promote_next_in_line

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemFields:
    name: str
    category: str
    replacement_value_paise: int
    condition_note: str = ""


def create_item(session: Session, *, fields: ItemFields, now: datetime) -> ItemView:
    with session.begin():
        item = Item(
            name=fields.name,
            category=fields.category,
            replacement_value_paise=fields.replacement_value_paise,
            condition_note=fields.condition_note,
            status=ItemStatus.AVAILABLE,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        session.flush()
        logger.info("item.created", extra={"item_id": item.id})
        return build_item_view(item, None, now)


def update_item(
    session: Session, *, item_id: int, changes: dict[str, object], now: datetime
) -> ItemView:
    """Edit descriptive fields. Status is never edited directly; it moves only through actions.

    A new replacement value applies to fees calculated from now on, including the
    return of a loan that is already out.
    """
    with session.begin():
        item = queries.get_item(session, item_id, for_update=True)
        for field_name, value in changes.items():
            setattr(item, field_name, value)
        item.updated_at = now
        session.flush()
        logger.info("item.updated", extra={"item_id": item.id, "fields": sorted(changes)})
        return build_item_view(item, queries.find_open_loan_for_item(session, item.id), now)


def delete_item(session: Session, *, item_id: int) -> None:
    with session.begin():
        item = queries.get_item(session, item_id, for_update=True)
        if queries.item_has_history(session, item.id):
            raise ConflictError(
                f"Item {item.id} has loan history and cannot be deleted; "
                "send it to maintenance instead.",
                code="ITEM_HAS_HISTORY",
                details={"item_id": item.id},
            )
        session.delete(item)
        logger.info("item.deleted", extra={"item_id": item_id})


def get_item(session: Session, *, item_id: int, now: datetime) -> ItemView:
    with session.begin():
        item = queries.get_item(session, item_id)
        return build_item_view(item, queries.find_open_loan_for_item(session, item.id), now)


def list_items(
    session: Session,
    *,
    now: datetime,
    status: ItemStatus | None,
    search: str | None,
    category: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ItemView], int]:
    with session.begin():
        rows, total = queries.list_items(
            session,
            now=now,
            status=status,
            search=search,
            category=category,
            limit=limit,
            offset=offset,
        )
        return [build_item_view(item, loan, now) for item, loan in rows], total


def list_categories(session: Session) -> list[str]:
    with session.begin():
        return queries.list_categories(session)


def send_to_maintenance(
    session: Session, *, item_id: int, now: datetime, condition_note: str | None
) -> ItemView:
    """Take an item out of circulation. An active reservation on it is cancelled."""
    with session.begin():
        item = queries.get_item(session, item_id, for_update=True)
        open_loan = settle_lapsed_reservation(session, item, now)
        status = effective_item_status(
            ItemStatus(item.status),
            open_loan.reserved_at if open_loan else None,
            open_loan.due_at if open_loan else None,
            now,
        )
        ensure_action_allowed(status, ItemAction.SEND_TO_MAINTENANCE, item_id=item.id)

        if open_loan is not None and open_loan.status == LoanStatus.RESERVED:
            open_loan.status = LoanStatus.CANCELLED
            open_loan.cancelled_at = now
            notify(
                session,
                member=open_loan.member,
                kind=Kind.RESERVATION_CANCELLED,
                loan_id=open_loan.id,
                now=now,
                message=(
                    f"Sorry, your reservation for {item.name} was cancelled because it needs "
                    "repair."
                ),
            )
            logger.info(
                "loan.cancelled_for_maintenance",
                extra={
                    "loan_id": open_loan.id,
                    "member_id": open_loan.member_id,
                    "item_id": item.id,
                },
            )
        item.status = ItemStatus.MAINTENANCE
        if condition_note is not None:
            item.condition_note = condition_note
        item.updated_at = now
        session.flush()
        logger.info("item.sent_to_maintenance", extra={"item_id": item.id})
        return build_item_view(item, None, now)


def return_to_service(
    session: Session, *, item_id: int, now: datetime, condition_note: str | None
) -> ItemView:
    with session.begin():
        item = queries.get_item(session, item_id, for_update=True)
        ensure_action_allowed(
            ItemStatus(item.status), ItemAction.RETURN_TO_SERVICE, item_id=item.id
        )
        item.status = ItemStatus.AVAILABLE
        if condition_note is not None:
            item.condition_note = condition_note
        item.updated_at = now
        session.flush()
        logger.info("item.returned_to_service", extra={"item_id": item.id})
        reserved_for_next = promote_next_in_line(session, item, now)
        return build_item_view(item, reserved_for_next, now)
